"""Testnet trading process (Faz 9, ADR 0015): canlı testnet verisi + saf çekirdek + GERÇEK testnet emirleri.

Paper'dan tek farkı execution adapter'ı: simülatör yerine `TestnetAdapter` (REST + HMAC, yalnızca
testnet.binancefuture.com). Kayıt, sıralama ve determinizm aynı; emir cevapları da aynı akışa yazılır.

Silahlanma (hepsi gerekli): FBOT_TESTNET_ARMED · .env anahtar çifti · config [mode].mode = "testnet".
Biri eksikse süreç emir göndermez, nedenini yazar ve yalnızca kayıt/analiz yapar.
Testnet sonuçları kârlılık kanıtı değildir.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import tomllib
from decimal import Decimal
from pathlib import Path

from fbot.core.engine import Engine
from fbot.core.order_state import OrderBook as OrderTracker
from fbot.execution.exchange_state import ReconcileSupervisor
from fbot.execution.queue import ExecutionQueue
from fbot.execution.testnet_adapter import TestnetAdapter, TestnetDisarmed
from fbot.gateway.killswitch import KillSwitch
from fbot.gateway.testnet import _HOST as TESTNET_HOST, TestnetClient, TestnetError, _http as default_http
from fbot.gateway.credfile import testnet_paths
from fbot.gateway.http_pool import HTTPPool
from fbot.testnet.arming import ArmingSupervisor
from fbot.paper.config import load_paper_config
from fbot.paper.main import PaperRecorder, filters_from_exchange_info, run_identity
from fbot.paper.config_view import effective_config
from fbot.paper.store import PaperStore
from fbot.persistence.writer import AsyncStore
from fbot.paper.trader import ORDER_CMDS, PaperTrader, _cmd_payload, _is_tick
from fbot.recorder.main import git_sha

ROOT = Path(__file__).resolve().parents[2]


class TestnetTrader(PaperTrader):
    """PaperTrader'ın execution'ı değişmiş hâli: komutlar simülatöre değil testnet'e gider."""

    def __init__(self, engine, adapter: TestnetAdapter, emit, store=None, queue: ExecutionQueue | None = None):
        super().__init__(engine, sim=_NullSim(), emit=emit, store=store)
        self.adapter = adapter
        self.orders = OrderTracker()
        self.errors = {"rejected": 0, "unknown": 0, "failed": 0, "dropped": 0}
        self.queue = queue            # None → legacy: gönderim olay yolunda, senkron (geri alma yolu)
        self.rtt_ns: list[int] = []   # gönderim RTT ölçümü (Gate 2.1)

    def _step(self, ev, now_ns: int) -> None:
        self.engine_state, cmds = self.engine.step(self.engine_state, ev, now_ns)
        for c in cmds:
            self.commands.append(c)
            if type(c).__name__ == "StateChanged":
                self.stats["state_changes"] += 1
                self.emit("ctrl", "state_changed", json.dumps({"symbol": c.symbol, "from_state": c.from_state,
                                                               "to_state": c.to_state, "bar_end_ms": c.bar_end_ms,
                                                               "confidence": c.confidence, "evidence": c.evidence,
                                                               "counter": c.counter}, separators=(",", ":")).encode(), now_ns, now_ns)
            elif isinstance(c, ORDER_CMDS):
                self._send(c, now_ns)
        self.stats["rejects"] = self.engine_state.intents_rejected
        self._record_verdicts()
        self._record_positions(force=_is_tick(ev))

    def _send(self, c, now_ns: int) -> None:
        payload = _cmd_payload(c)
        cev = self.emit("ctrl", "command", json.dumps(payload, separators=(",", ":")).encode(), now_ns, now_ns)
        if self.store is not None:
            self.store.record_order({**payload, "seq": cev.seq, "t_ns": now_ns})
        if self.queue is not None:
            accepted, klass = self.queue.put(c, now_ns)
            if not accepted:
                # Sıkışıklıkta önce giriş reddedilir; koruma/çıkış için rezerv slot durur.
                self.errors["dropped"] += 1
                self.emit("ctrl", "order_dropped", json.dumps({"cmd": payload["cmd"], "class": klass,
                                                               "queue": self.queue.stats}, separators=(",", ":"), default=str).encode(), now_ns, now_ns)
            return
        self._send_now(c, payload, now_ns)

    def on_send_result(self, c, klass: str, out: dict | None, err: Exception | None, queued_ns: int, rtt_ns: int) -> None:
        """Kuyruk işçisinden gelen sonuç; döngü thread'inde çalışır ve tek sıralama noktasına yazar."""
        self.rtt_ns.append(rtt_ns)
        del self.rtt_ns[10_000:]
        now_ns = queued_ns
        if err is not None:
            self._send_error(err, _cmd_payload(c), now_ns)
            return
        self._emit_send_result(out, now_ns)

    def _send_error(self, e: Exception, payload: dict, now_ns: int) -> None:
        if isinstance(e, TestnetDisarmed):
            self.emit("ctrl", "order_skipped", json.dumps({"reason": str(e), "cmd": payload["cmd"]}, separators=(",", ":")).encode(), now_ns, now_ns)
            return
        if isinstance(e, TestnetError):
            self.errors["failed"] += 1
            self.emit("ctrl", "order_failed", json.dumps({"status": e.status, "code": e.code, "msg": str(e)[:200],
                                                          "unknown_execution": e.unknown_execution,
                                                          "cmd": payload["cmd"]}, separators=(",", ":")).encode(), now_ns, now_ns)
            return
        raise e

    def _emit_send_result(self, out: dict, now_ns: int) -> None:
        kind = out.get("kind", "")
        if kind.endswith("_rejected"):
            self.errors["rejected"] += 1
        elif kind.endswith("_unknown"):
            self.errors["unknown"] += 1
        if kind.startswith("order"):
            self.stats["orders"] += 1
        elif kind.startswith("algo"):
            self.stats["algos"] += 1
        self.emit("exec", kind, json.dumps(out, separators=(",", ":"), default=str).encode(), now_ns, now_ns)

    def _send_now(self, c, payload: dict, now_ns: int) -> None:
        """Legacy yol: HTTP isteği olay işleme yolunun içinde (bloklar). `transport = "legacy"`."""
        try:
            out = self.adapter.submit(c, now_ms=now_ns // 1_000_000)
        except (TestnetDisarmed, TestnetError) as e:
            self._send_error(e, payload, now_ns)
            return
        self._emit_send_result(out, now_ns)

    def on_user_event(self, mapped: dict, now_ns: int) -> None:
        """User data akışından gelen olay: emir durumu güncellenir, çekirdeğe exec olayı olarak verilir."""
        kind = mapped.get("kind")
        if kind in ("order_fill", "order_ack", "order_done"):
            self.orders.apply({**mapped, "trade_id": mapped.get("trade_id")})
        ev = self.emit("exec", kind, json.dumps(mapped, separators=(",", ":"), default=str).encode(), now_ns, now_ns)
        super()._step(ev, now_ns) if False else self._step(ev, now_ns)


class _NullSim:
    """Testnet'te simülatör yok; PaperTrader'ın çağrılarını yutar."""
    pending_orders: list = []
    triggered: list = []

    def on_depth(self, *a, **k): pass
    def on_book(self, *a, **k): pass
    def on_mark(self, *a, **k): return []
    def poll(self, *a, **k): return []
    def submit(self, *a, **k): pass
    def set_position(self, *a, **k): pass


class TestnetRecorder(PaperRecorder):
    async def resolve_universe(self):
        syms = await asyncio.to_thread(lambda: list(self.pcfg.recorder.symbols))
        from fbot.gateway.rest import exchange_info
        ex = await asyncio.to_thread(exchange_info)
        core = self.pcfg.core
        core = type(core)(**{**core.__dict__, "filters": filters_from_exchange_info(ex, set(syms))})
        # Adapter borsa filtreleriyle çalışır (step_size / tick_size); pricePrecision kullanılmaz (Gate 2.0)
        # Silahsız doğar; anahtar dosyasını denetçi okur ve gerekirse çalışırken silahlandırır
        adapter = TestnetAdapter(None, armed=False, symbols=core.filters)
        ex = self.pcfg.execution
        self.queue = ExecutionQueue(maxsize=ex.queue_max, reserve_slots=ex.reserve_slots) if ex.transport == "persistent_async" else None
        self.trader = TestnetTrader(Engine(core), adapter,
                                    lambda cat, stream, raw, recv_ns=None, mono_ns=None: self.emit(cat, stream, raw, recv_ns, mono_ns, notify=False),
                                    store=self.store, queue=self.queue)
        self.arming = ArmingSupervisor(
            env_path=testnet_paths(ROOT), adapter=adapter,
            make_client=lambda creds: TestnetClient(creds, http=self._transport(), reserve_orders=self.pcfg.core.risk.reserve_orders),
            probe=self._probe_balance,
            open_positions=lambda: sum(1 for p in self.trader.engine_state.positions.values() if p.state.value != "CLOSED"))
        ev = self.arming.check()
        armed, why = adapter.armed, (ev or {}).get("reason", "—")
        if ev:
            self._emit_arming(ev)
        # Açılışta mutabakat (CLAUDE.md mutlak kuralı): borsa tek doğruluk kaynağı, farkta kilit
        lev = {s2: core.risk.leverage.get(s2, core.risk.default_leverage) for s2 in syms}
        self.recon = ReconcileSupervisor(client=adapter.client, symbols=set(syms),
                                         positions=lambda: self.trader.engine_state.positions,
                                         expected_leverage=lev)
        self._reconcile(lambda: int(time.time() * 1000))
        if self.pcfg.cost_drift is not None:
            from fbot.core.cost_drift import CostDriftMonitor
            self.trader.drift = CostDriftMonitor(self.pcfg.cost_drift)
        self.trader.engine_state.kill_switch = self.kill.active
        self.ctrl("testnet_start", {"armed": armed, "why": why, "symbols": syms,
                                    "cells": [c.key() for c in core.decision.allowed_cells],
                                    "note": "testnet tesisat doğrulama ortamıdır; kârlılık kanıtı değildir (ADR 0015)"}, notify=False)
        return syms

    def _transport(self):
        """`persistent_async`: kalıcı bağlantı havuzu (TLS el sıkışması bağlantı başına).
        `legacy`: her istekte yeni bağlantı (`TestnetClient` varsayılanı)."""
        if self.pcfg.execution.transport != "persistent_async":
            return default_http
        ex = self.pcfg.execution
        self.pool = HTTPPool(TESTNET_HOST, connect_timeout_s=ex.connect_timeout_ms / 1000,
                             read_timeout_s=ex.read_timeout_ms / 1000)
        return self.pool.as_callable()

    def _exec_stats(self) -> dict | None:
        """Gate 2.1 ölçümü: kuyruk derinliği, reddedilen giriş sayısı, gönderim RTT'si, TLS el sıkışması."""
        if self.queue is None:
            return None
        r = sorted(self.trader.rtt_ns) if self.trader is not None else []
        def pct(q):
            return round(r[min(len(r) - 1, int(q * (len(r) - 1) + 0.5))] / 1e6, 1) if r else None
        out = {**self.queue.stats, "rtt_ms": {"n": len(r), "p50": pct(0.5), "p95": pct(0.95), "p99": pct(0.99)}}
        if getattr(self, "pool", None) is not None:
            out["pool"] = dict(self.pool.stats)
        return out

    def _probe_balance(self, client) -> float:
        """Silahlanma kanıtı: yeni anahtarla bakiye okunabiliyor mu? Hesap görünümünü de günceller."""
        bal = client.balance(int(time.time() * 1000))
        usdt = next((float(b["balance"]) for b in bal if b.get("asset") == "USDT"), 0.0)
        self.pcfg.core.account["available_balance"] = str(usdt)
        return usdt

    def _reconcile(self, now_ms) -> None:
        """Açılış mutabakatı (senkron; henüz döngü yok). Periyodik yol `_pre_beat`."""
        self.recon.client = self.trader.adapter.client        # silahlanma değiştiyse istemci de değişti
        self._apply_reconcile(self.recon.check(now_ms))

    def _apply_reconcile(self, ev) -> None:
        """Mutabakat sonucunu çekirdeğe ve kayda yazar. Kilit çekirdekte: K2 her girişi reddeder."""
        if ev is None:
            return
        self._recon_state = ev
        self.trader.engine_state.reconciled = ev["reconciled"]
        self.ctrl("reconcile", ev, notify=False)
        print(json.dumps({"msg": "reconcile", **ev}, ensure_ascii=False), flush=True)

    def _emit_arming(self, ev: dict) -> None:
        """Silahlanma değişikliğini kayda ve konsola yazar. Gizli anahtar yazılmaz (yalnızca maske)."""
        self._arming_reason = ev.get("reason")
        self.ctrl(ev["kind"], ev, notify=False)
        print(json.dumps({"msg": ev["kind"], **ev}, ensure_ascii=False), flush=True)

    async def main(self):
        if self.queue is not None:
            # İşçi, evren çözüldükten sonra (trader hazırken) başlatılır
            self._queue_task = None
        await super().main()
        if self.queue is not None:
            await self.queue.aclose()
        if getattr(self, "pool", None) is not None:
            self.pool.close()

    async def paper_status_task(self):
        """Kuyruk işçisi ilk durum turunda başlatılır: trader o an hazırdır."""
        if self.queue is not None and self.trader is not None:
            self.queue.start(lambda c, now_ns: self.trader.adapter.submit(c, now_ms=now_ns // 1_000_000),
                             self.trader.on_send_result)
        await super().paper_status_task()

    async def _pre_beat(self) -> None:
        """Silahlanma denetimi ve mutabakat **REST çağrısıdır**: olay döngüsünde çalışırsa loop lag
        dikeni üretir (Gate 1 ölçümünde en kötü p99 3,2 s). Thread'e taşınır; sonuçların akışa
        yazımı yine döngü thread'inde olur (tek sıralama noktası)."""
        try:
            ev = await asyncio.to_thread(self.arming.check)
            if ev:
                self._emit_arming(ev)
        except Exception as e:  # noqa: BLE001 — denetçi hatası kaydı durdurmaz
            print(json.dumps({"msg": "arming_error", "err": repr(e)}), flush=True)
        try:
            self.recon.client = self.trader.adapter.client
            ev = await asyncio.to_thread(self.recon.check, lambda: int(time.time() * 1000))
            self._apply_reconcile(ev)
        except Exception as e:  # noqa: BLE001 — mutabakat hatası kaydı durdurmaz, kilidi açmaz
            self.trader.engine_state.reconciled = False
            print(json.dumps({"msg": "reconcile_error", "err": repr(e)}), flush=True)

    def _beat(self, kill: bool) -> None:
        """Canlılık damgası. Bloklayan sorgular `_pre_beat`'te, thread'te yapıldı."""
        st = self.trader.engine_state
        self.store.heartbeat(now_ns=time.time_ns(),
                             detail={"kill_switch": kill, "positions": len(st.positions), "stats": dict(self.trader.stats),
                                     "open": sum(1 for p in st.positions.values() if p.state.value != "CLOSED"),
                                     "armed": self.trader.adapter.armed,
                                     "arming_reason": getattr(self, "_arming_reason", None),
                                     # Konsolun "sistem bağlantı durumu" tablosu bunları okur
                                     "orders": len(self.trader.orders.orders),
                                     "fills": self.trader.orders._stats["fills"],
                                     "rejected": self.trader.errors["rejected"],
                                     "persist": self._persist_stats(),
                                     "execution": self._exec_stats(),
                                     "reconciled": getattr(self, "_recon_state", {}).get("reconciled"),
                                     "reconcile_reason": getattr(self, "_recon_state", {}).get("reason"),
                                     "mismatches": getattr(self, "_recon_state", {}).get("mismatches") or []})


def parse(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/testnet.toml")
    p.add_argument("--run-id", default=os.environ.get("FBOT_RUN_ID"))
    p.add_argument("--duration", type=float, default=None)
    return p.parse_args(argv)


def main(argv):
    a = parse(argv)
    cfg, h = load_paper_config(a.config)
    mode = tomllib.loads(Path(a.config).read_bytes().decode()).get("mode", {}).get("mode")
    if mode != "testnet":
        raise SystemExit(f"config [mode].mode 'testnet' değil ({mode}): testnet süreci başlatılmaz")
    run_id = a.run_id or time.strftime("testnet-%Y%m%dT%H%M%SZ", time.gmtime())
    db = Path(cfg.recorder.out_dir) / run_id / "paper.db"
    ident = run_identity(cfg, h, run_id, "testnet", Path(cfg.recorder.out_dir) / run_id)
    store = AsyncStore(PaperStore(db, identity=ident, started_ns=time.time_ns()))
    store.set_config({"config_path": a.config, "git_sha": git_sha(), **effective_config(cfg)},
                     config_hash=h, config_semantic_hash=ident.config_semantic_hash)
    print(json.dumps({"msg": "testnet start", **ident.as_dict(),
                      "armed_env": bool(os.environ.get("FBOT_TESTNET_ARMED")),
                      "hot_reload": "anahtar .env'den 10 s'de bir okunur; yeniden başlatma gerekmez",
                      "note": "yalnızca testnet.binancefuture.com; kârlılık kanıtı değildir"}), flush=True)
    asyncio.run(TestnetRecorder(cfg, h, run_id, a.duration, store, config_path=a.config).main())
    print(json.dumps({"msg": "testnet stop", "summary": store.summary(), "persist": store.stats}, default=str), flush=True)
    store.close()


if __name__ == "__main__":
    main(sys.argv[1:])
