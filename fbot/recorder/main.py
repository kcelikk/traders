"""Recorder process: gateway (kategori bağlantıları) + tek sıralama noktası + write-behind gzip kayıt.

Tek thread, tek asyncio döngüsü. Disk yazımı aynı döngüde ayrı görevde (kuyruk), REST çağrıları to_thread.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from fbot.config import load_recorder_config
from fbot.events import stream_of
from fbot.gateway.rest import depth_raw, exchange_info, ticker_24h
from fbot.gateway.ws_category import CategoryConnection
from fbot.recorder.writer import RotatingGzipWriter
from fbot.sequencer import Sequencer
from fbot.universe import select_top
from scripts.latency_core import percentiles

WS_BASE = "wss://fstream.binance.com"


def git_sha() -> str:
    sha = os.environ.get("FBOT_GIT_SHA")
    if sha:
        return sha
    try:
        return subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def last_seq_from_manifest(out: Path) -> tuple[int, int]:
    """(son seq, önceki başlangıç sayısı). Yeniden başlatmada seq kaldığı yerden sürer."""
    m = out / "manifest.jsonl"
    last = 0
    if m.exists():
        for line in m.read_text().splitlines():
            if line.strip():
                last = max(last, json.loads(line)["last_seq"] or 0)
    starts = 0
    r = out / "runs.jsonl"
    if r.exists():
        starts = sum(1 for l in r.read_text().splitlines() if l.strip())
    return last, starts


class Recorder:
    def __init__(self, cfg, cfg_hash: str, run_id: str, duration: float | None):
        self.cfg = cfg
        self.cfg_hash = cfg_hash
        self.run_id = run_id
        self.duration = duration
        self.out = Path(cfg.out_dir) / run_id
        self.out.mkdir(parents=True, exist_ok=True)
        start_seq, self.restart_no = last_seq_from_manifest(self.out)
        self.seq = Sequencer(start=start_seq)
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=500_000)
        self.dropped = 0
        self.frames = {"public": 0, "market": 0}
        self.stop_ev = asyncio.Event()
        self.conns: dict[str, CategoryConnection] = {}
        self.writer = RotatingGzipWriter(self.out, rotate_s=cfg.rotate_minutes * 60)
        self.lag_samples: list[float] = []
        self.stale_flag = {"public": False, "market": False}
        self.symbols: list[str] = []

    # ---- tek sıralama noktası
    def emit(self, cat: str, stream: str, raw: bytes, recv_ns: int | None = None, mono_ns: int | None = None):
        ev = self.seq.next(recv_ns or time.time_ns(), mono_ns or time.monotonic_ns(), cat, stream, raw)
        try:
            self.queue.put_nowait(ev)
        except asyncio.QueueFull:
            self.dropped += 1  # asla sessiz değil: stats'ta raporlanır

    def ctrl(self, kind: str, info: dict):
        self.emit("ctrl", kind, json.dumps(info, separators=(",", ":")).encode())

    def on_frame_for(self, cat: str):
        def on_frame(raw: bytes, recv_ns: int, mono_ns: int):
            self.frames[cat] += 1
            self.emit(cat, stream_of(raw) or "?", raw, recv_ns, mono_ns)
        return on_frame

    # ---- görevler
    async def writer_task(self):
        last_flush = time.monotonic()
        while True:
            ev = await self.queue.get()
            self.writer.write(ev)
            now = time.monotonic()
            if now - last_flush > 5.0:
                self.writer.flush()
                last_flush = now
            self.queue.task_done()

    async def snapshot_task(self):
        while not self.stop_ev.is_set():
            for sym in self.symbols:
                if self.stop_ev.is_set():
                    break
                t0 = time.monotonic_ns()
                try:
                    st, hdr, body = await asyncio.to_thread(depth_raw, sym, self.cfg.depth_snapshot_limit)
                    head = json.dumps({"symbol": sym, "status": st, "used_weight_1m": hdr.get("x-mbx-used-weight-1m"),
                                       "rtt_ms": (time.monotonic_ns() - t0) // 10**6}, separators=(",", ":")).encode()
                    raw = head[:-1] + b',"body":' + (body if st == 200 else json.dumps(body.decode(errors="replace")).encode()) + b"}"
                    self.emit("ctrl", "snapshot", raw)
                except Exception as e:  # noqa: BLE001
                    self.ctrl("snapshot_error", {"symbol": sym, "err": repr(e)})
                await asyncio.sleep(0.5)  # ağırlık 20/sembol; 2400/dk limitinin çok altında
            try:
                await asyncio.wait_for(self.stop_ev.wait(), timeout=self.cfg.snapshot_interval_s)
            except asyncio.TimeoutError:
                pass

    async def staleness_task(self):
        while not self.stop_ev.is_set():
            await asyncio.sleep(1.0)
            now = time.monotonic_ns()
            for cat, conn in self.conns.items():
                thr = self.cfg.staleness_s.get(cat)
                if thr is None or conn.last_frame_mono_ns == 0:
                    continue
                age = (now - conn.last_frame_mono_ns) / 1e9
                if age > thr and not self.stale_flag[cat]:
                    self.stale_flag[cat] = True
                    self.ctrl("stale", {"cat": cat, "age_s": round(age, 1), "threshold_s": thr})
                    await conn.force_reconnect("stale")
                elif age <= thr:
                    self.stale_flag[cat] = False

    async def stats_task(self):
        interval = 0.1
        last_stats = time.monotonic()
        while not self.stop_ev.is_set():
            t0 = time.monotonic()
            await asyncio.sleep(interval)
            self.lag_samples.append((time.monotonic() - t0 - interval) * 1000)
            if time.monotonic() - last_stats >= self.cfg.stats_interval_s:
                p = percentiles(self.lag_samples)
                self.ctrl("stats", {
                    "loop_lag_ms": {"p50": round(p["p50"], 2), "p99": round(p["p99"], 2), "max": round(max(self.lag_samples), 2), "n": len(self.lag_samples)},
                    "queue": self.queue.qsize(), "dropped": self.dropped, "seq": self.seq.last_seq,
                    "frames": dict(self.frames), "connects": {c: k.connects for c, k in self.conns.items()},
                    "file": self.writer.current_file,
                })
                self.lag_samples.clear()
                last_stats = time.monotonic()

    async def resolve_universe(self) -> list[str]:
        if self.cfg.mode == "list":
            return list(self.cfg.symbols)
        ex, tk = await asyncio.gather(asyncio.to_thread(exchange_info), asyncio.to_thread(ticker_24h))
        return select_top(ex["symbols"], tk, self.cfg.top_n, self.cfg.exclude_bases)

    async def main(self):
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self.stop_ev.set)
        self.symbols = await self.resolve_universe()
        streams = {
            "public": [t.format(s=s.lower()) for s in self.symbols for t in self.cfg.public_streams],
            "market": [t.format(s=s.lower()) for s in self.symbols for t in self.cfg.market_streams],
        }
        start_info = {"run_id": self.run_id, "restart_no": self.restart_no, "git_sha": git_sha(), "config_hash": self.cfg_hash,
                      "symbols": self.symbols, "streams": streams, "start_ns": time.time_ns(), "seq_start": self.seq.last_seq,
                      "pid": os.getpid()}
        with (self.out / "runs.jsonl").open("a") as f:
            f.write(json.dumps(start_info) + "\n")
        self.ctrl("run_start", start_info)
        for cat in ("public", "market"):
            url = f"{WS_BASE}/{cat}/stream?streams=" + "/".join(streams[cat])
            self.conns[cat] = CategoryConnection(cat, url, self.on_frame_for(cat), self.ctrl,
                                                 self.cfg.backoff_initial_s, self.cfg.backoff_max_s)
        wt = asyncio.create_task(self.writer_task())
        tasks = [asyncio.create_task(c.run()) for c in self.conns.values()]
        tasks += [asyncio.create_task(self.snapshot_task()), asyncio.create_task(self.staleness_task()), asyncio.create_task(self.stats_task())]
        print(json.dumps({"msg": "recorder started", **{k: v for k, v in start_info.items() if k != "streams"}}), flush=True)
        try:
            await asyncio.wait_for(self.stop_ev.wait(), timeout=self.duration)
        except asyncio.TimeoutError:
            self.stop_ev.set()
        for c in self.conns.values():
            c.stop()
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.ctrl("run_end", {"seq": self.seq.last_seq, "frames": self.frames, "dropped": self.dropped})
        await self.queue.join()
        wt.cancel()
        self.writer.close()
        print(json.dumps({"msg": "recorder stopped", "seq": self.seq.last_seq, "frames": self.frames, "dropped": self.dropped}), flush=True)


def parse(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/recorder.toml")
    p.add_argument("--run-id", default=os.environ.get("FBOT_RUN_ID") or time.strftime("rec-%Y%m%dT%H%M%SZ", time.gmtime()))
    p.add_argument("--duration", type=float, default=None, help="saniye; verilmezse sinyale kadar")
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse(sys.argv[1:])
    cfg, h = load_recorder_config(a.config)
    asyncio.run(Recorder(cfg, h, a.run_id, a.duration).main())
