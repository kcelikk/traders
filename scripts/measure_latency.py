"""Faz 0 gecikme ölçümü — I/O kenarı.

Ölçülenler (hepsi JSONL, data/latency/<run_id>/):
  rest_keepalive.jsonl  GET /fapi/v1/time, kalıcı TLS bağlantı, rtt + clock skew
  rest_newconn.jsonl    aynı istek, her seferinde yeni TCP+TLS
  ws_public.jsonl       /public bookTicker: recv - E, recv - T, parse süresi
  ws_market.jsonl       /market aggTrade + markPrice@1s: aynı
  ws_api.jsonl          ws-fapi 'depth' (limit 5, kimliksiz, ağırlık 2): istek→cevap
  events.jsonl          bağlantı, kopma, hata, yeniden bağlanma

Doküman kaynakları: docs/binance-api-verification.md
"""
from __future__ import annotations

import argparse
import asyncio
import http.client
import json
import signal
import sys
import time
import uuid
from pathlib import Path

from websockets.asyncio.client import connect

from scripts.latency_core import rest_sample, ws_lag

REST_HOST = "fapi.binance.com"
REST_TIME_PATH = "/fapi/v1/time"
WS_PUBLIC = "wss://fstream.binance.com/public/stream?streams="
WS_MARKET = "wss://fstream.binance.com/market/stream?streams="
WS_API = "wss://ws-fapi.binance.com/ws-fapi/v1"


def wall_ms() -> int:
    return time.time_ns() // 1_000_000


class Writer:
    def __init__(self, path: Path):
        self.f = path.open("a", buffering=1 << 16)
        self.n = 0

    def write(self, rec: dict):
        self.f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        self.n += 1
        if self.n % 200 == 0:
            self.f.flush()

    def close(self):
        self.f.flush()
        self.f.close()


class Run:
    def __init__(self, out_dir: Path, symbols: list[str], args):
        self.out = out_dir
        self.symbols = [s.lower() for s in symbols]
        self.args = args
        self.only = set(args.only.split(",")) if args.only else None
        names = ["rest_keepalive", "rest_newconn", "ws_public", "ws_market", "ws_api"]
        self.active = [n for n in names if self.only is None or n in self.only]
        self.w = {name: Writer(out_dir / f"{name}.jsonl") for name in self.active}
        for name in ("ws_public", "ws_market"):
            if name in self.active:
                self.w[name + "_rate"] = Writer(out_dir / f"{name}_rate.jsonl")
        self.w["events"] = Writer(out_dir / "events.jsonl")
        self.stop = asyncio.Event()

    def event(self, kind: str, **kw):
        self.w["events"].write({"wall_ms": wall_ms(), "kind": kind, **kw})

    # ---------------- REST ----------------
    @staticmethod
    def _rest_time_once(conn: http.client.HTTPSConnection) -> tuple[int, int, int | None, int]:
        t0 = wall_ms()
        conn.request("GET", REST_TIME_PATH)
        resp = conn.getresponse()
        body = resp.read()
        t1 = wall_ms()
        st = None
        if resp.status == 200:
            st = json.loads(body).get("serverTime")
        return t0, t1, st, resp.status

    async def rest_keepalive(self):
        conn = None
        while not self.stop.is_set():
            try:
                if conn is None:
                    conn = http.client.HTTPSConnection(REST_HOST, timeout=10)
                    self.event("rest_keepalive_connect")
                t0, t1, st, status = await asyncio.to_thread(self._rest_time_once, conn)
                rec = rest_sample(t0, t1, st)
                rec["http"] = status
                self.w["rest_keepalive"].write(rec)
            except Exception as e:  # noqa: BLE001
                self.event("rest_keepalive_error", err=repr(e))
                try:
                    conn.close()
                except Exception:  # noqa: BLE001
                    pass
                conn = None
            await asyncio.sleep(self.args.rest_interval)

    @staticmethod
    def _rest_newconn_once() -> dict:
        c0 = wall_ms()
        conn = http.client.HTTPSConnection(REST_HOST, timeout=10)
        conn.connect()
        c1 = wall_ms()
        t0, t1, st, status = Run._rest_time_once(conn)
        conn.close()
        rec = rest_sample(t0, t1, st)
        rec["connect_ms"] = c1 - c0
        rec["total_ms"] = t1 - c0
        rec["http"] = status
        return rec

    async def rest_newconn(self):
        while not self.stop.is_set():
            try:
                rec = await asyncio.to_thread(self._rest_newconn_once)
                self.w["rest_newconn"].write(rec)
            except Exception as e:  # noqa: BLE001
                self.event("rest_newconn_error", err=repr(e))
            await asyncio.sleep(self.args.newconn_interval)

    # ---------------- WS market streams ----------------
    async def ws_stream(self, name: str, base: str, streams: list[str]):
        url = base + "/".join(streams)
        w = self.w[name]
        wr = self.w[name + "_rate"]
        sample = max(1, self.args.ws_sample)
        counts: dict[str, list[int]] = {}  # stream -> [n, bytes]
        cur_sec = None
        seq = 0
        while not self.stop.is_set():
            c0 = wall_ms()
            try:
                async with connect(url, max_queue=4096) as ws:
                    self.event(f"{name}_connect", connect_ms=wall_ms() - c0, url=url)
                    async for raw in ws:
                        recv = wall_ms()
                        p0 = time.perf_counter_ns()
                        msg = json.loads(raw)
                        parse_us = (time.perf_counter_ns() - p0) / 1000
                        rec = ws_lag(msg, recv)
                        if rec is None:
                            continue
                        # saniyelik sayaç (örneklemeden bağımsız, tüm mesajlar)
                        sec = recv // 1000
                        if sec != cur_sec:
                            for st, (n, b) in counts.items():
                                wr.write({"wall_ms": cur_sec * 1000, "stream": st, "n": n, "bytes": b})
                            counts = {}
                            cur_sec = sec
                        c = counts.setdefault(rec["stream"], [0, 0])
                        c[0] += 1
                        c[1] += len(raw)
                        seq += 1
                        if seq % sample != 0:
                            continue
                        rec["parse_us"] = parse_us
                        rec["bytes"] = len(raw)
                        w.write(rec)
                        if self.stop.is_set():
                            break
            except Exception as e:  # noqa: BLE001
                self.event(f"{name}_disconnect", err=repr(e))
                await asyncio.sleep(1.0)

    # ---------------- WS API ----------------
    async def ws_api(self):
        w = self.w["ws_api"]
        sym = self.symbols[0].upper()
        while not self.stop.is_set():
            c0 = wall_ms()
            try:
                async with connect(WS_API) as ws:
                    self.event("ws_api_connect", connect_ms=wall_ms() - c0)
                    while not self.stop.is_set():
                        rid = uuid.uuid4().hex
                        req = {"id": rid, "method": "depth", "params": {"symbol": sym, "limit": 5}}
                        t0 = wall_ms()
                        await ws.send(json.dumps(req))
                        raw = await asyncio.wait_for(ws.recv(), timeout=10)
                        t1 = wall_ms()
                        msg = json.loads(raw)
                        if msg.get("id") != rid:
                            self.event("ws_api_id_mismatch")
                            continue
                        res = msg.get("result") or {}
                        rec = {
                            "wall_ms": t0,
                            "rtt_ms": t1 - t0,
                            "status": msg.get("status"),
                            "E": res.get("E"),
                            "T": res.get("T"),
                            "lag_E_ms": (t1 - res["E"]) if res.get("E") else None,
                            "rateLimits": msg.get("rateLimits"),
                        }
                        w.write(rec)
                        await asyncio.sleep(self.args.wsapi_interval)
            except Exception as e:  # noqa: BLE001
                self.event("ws_api_disconnect", err=repr(e))
                await asyncio.sleep(1.0)

    async def main(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop.set)
        self.event("run_start", symbols=self.symbols, args=vars(self.args))
        public = [f"{s}@bookTicker" for s in self.symbols]
        market = [f"{s}@aggTrade" for s in self.symbols] + [f"{s}@markPrice@1s" for s in self.symbols]
        factories = {
            "rest_keepalive": self.rest_keepalive,
            "rest_newconn": self.rest_newconn,
            "ws_public": lambda: self.ws_stream("ws_public", WS_PUBLIC, public),
            "ws_market": lambda: self.ws_stream("ws_market", WS_MARKET, market),
            "ws_api": self.ws_api,
        }
        tasks = [asyncio.create_task(factories[n]()) for n in self.active]
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=self.args.duration)
        except asyncio.TimeoutError:
            self.stop.set()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.event("run_end")
        for w in self.w.values():
            w.close()


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--duration", type=float, default=3600, help="saniye")
    p.add_argument("--symbols", default="BTCUSDT,ETHUSDT")
    p.add_argument("--out-root", default="data/latency")
    p.add_argument("--run-id", default=None)
    p.add_argument("--rest-interval", type=float, default=2.0)
    p.add_argument("--newconn-interval", type=float, default=30.0)
    p.add_argument("--wsapi-interval", type=float, default=5.0)
    p.add_argument("--ws-sample", type=int, default=1, help="WS mesajlarından her N'incisini kaydet (hız sayacı etkilenmez)")
    p.add_argument("--only", default=None, help="virgülle: rest_keepalive,rest_newconn,ws_public,ws_market,ws_api")
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse_args(sys.argv[1:])
    run_id = a.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    out_dir = Path(a.out_root) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"run_id={run_id} out={out_dir}", flush=True)
    asyncio.run(Run(out_dir, a.symbols.split(","), a).main())
    print("done", flush=True)
