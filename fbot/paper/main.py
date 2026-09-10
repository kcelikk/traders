"""Paper trading process (Faz 7): kayıt + saf çekirdek + simüle execution, tek process tek thread.

Gerçek emir gönderilmez (`LiveExecutionAdapter` korumalı stub). Üretilen kayıt kendi kendine yeterlidir:
market olayları, kararlar, komutlar ve simüle dolumlar aynı sıralı akışta; replay bit-eşit doğrular.
Kârlılık gösterilmedi (ADR 0010).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from decimal import Decimal
from pathlib import Path

from fbot.core.engine import Engine
from fbot.core.position import Filters
from fbot.execution.sim import SimConfig, SimExecutor
from fbot.gateway.killswitch import KillSwitch
from fbot.gateway.rest import exchange_info
from fbot.paper.config import load_paper_config
from fbot.paper.store import PaperStore
from fbot.paper.trader import PaperTrader
from fbot.recorder.main import Recorder, git_sha

ROOT = Path(__file__).resolve().parents[2]


def filters_from_exchange_info(ex: dict, symbols: set[str]) -> dict[str, Filters]:
    out = {}
    for s in ex["symbols"]:
        if s["symbol"] not in symbols:
            continue
        f = {x["filterType"]: x for x in s["filters"]}
        out[s["symbol"]] = Filters(step_size=Decimal(f["LOT_SIZE"]["stepSize"]), min_qty=Decimal(f["LOT_SIZE"]["minQty"]),
                                   min_notional=Decimal(f["MIN_NOTIONAL"]["notional"]), tick_size=Decimal(f["PRICE_FILTER"]["tickSize"]))
    return out


class PaperRecorder(Recorder):
    """Recorder + trader: evren çözüldükten sonra filtreleri yükler ve trader'ı bağlar."""

    def __init__(self, pcfg, cfg_hash, run_id, duration, store: PaperStore):
        super().__init__(pcfg.recorder, cfg_hash, run_id, duration)
        self.pcfg = pcfg
        self.store = store
        self.kill = KillSwitch(ROOT / "data" / "state" / "kill_switch.json")

    async def resolve_universe(self):
        syms = await super().resolve_universe()
        ex = await asyncio.to_thread(exchange_info)
        core = self.pcfg.core
        core = type(core)(**{**core.__dict__, "filters": filters_from_exchange_info(ex, set(syms))})
        engine = Engine(core)
        self.trader = PaperTrader(engine, SimExecutor(SimConfig(latency_ms=self.pcfg.sim_latency_ms, seed=self.pcfg.sim_seed, jitter_ms=self.pcfg.sim_jitter_ms,
                                                                partial_timeout_ms=self.pcfg.sim_partial_timeout_ms,
                                                                prob_fill_on_touch=self.pcfg.sim_prob_fill_on_touch)),
                                  lambda cat, stream, raw, recv_ns=None, mono_ns=None: self.emit(cat, stream, raw, recv_ns, mono_ns, notify=False),
                                  store=self.store)
        self.trader.book_levels = self.pcfg.sim_book_levels
        self.trader.engine_state.kill_switch = self.kill.active
        self.ctrl("paper_start", {"cells": [c.key() for c in core.decision.allowed_cells], "notional": str(core.decision.notional_usdt),
                                  "kill_switch": self.kill.active, "sim_latency_ms": self.pcfg.sim_latency_ms,
                                  "sim_seed": self.pcfg.sim_seed, "filters": len(core.filters), "note": "kârlılık gösterilmedi (ADR 0010)"}, notify=False)
        return syms

    async def paper_status_task(self):
        """Kill switch dosyasını izler ve periyodik özet yayar (hot path'te değil)."""
        while not self.stop_ev.is_set():
            await asyncio.sleep(10.0)
            ks = KillSwitch(self.kill.path)
            if self.trader is not None:
                self.trader.engine_state.kill_switch = ks.active
                st = self.trader.engine_state
                self.store.flush()
                self.ctrl("paper_stats", {**self.trader.stats, "positions": len(st.positions),
                                          "open": sum(1 for p in st.positions.values() if p.state.value not in ("CLOSED",)),
                                          "intents": st.intents_made, "rejected": st.intents_rejected,
                                          "kill_switch": ks.active}, notify=False)

    async def main(self):
        self._extra_task = None
        orig = self.stats_task

        async def stats_and_status():
            await asyncio.gather(orig(), self.paper_status_task())
        self.stats_task = stats_and_status
        await super().main()
        self.store.flush()


def parse(argv):
    p = argparse.ArgumentParser()
    p.add_argument("--config", default="config/paper.toml")
    p.add_argument("--run-id", default=os.environ.get("FBOT_RUN_ID"))
    p.add_argument("--duration", type=float, default=None)
    p.add_argument("--db", default=None)
    return p.parse_args(argv)


def main(argv):
    a = parse(argv)
    cfg, h = load_paper_config(a.config)
    run_id = a.run_id or time.strftime("paper-%Y%m%dT%H%M%SZ", time.gmtime())
    db = Path(a.db or (Path(cfg.recorder.out_dir) / run_id / "paper.db"))
    store = PaperStore(db, run_id=run_id)
    print(json.dumps({"msg": "paper start", "run_id": run_id, "config_hash": h, "git_sha": git_sha(), "db": str(db),
                      "cells": [c.key() for c in cfg.core.decision.allowed_cells],
                      "note": "allowed_cells boşsa giriş emri üretilmez (ADR 0010)"}), flush=True)
    asyncio.run(PaperRecorder(cfg, h, run_id, a.duration, store).main())
    print(json.dumps({"msg": "paper stop", "summary": store.summary()}, default=str), flush=True)
    store.close()


if __name__ == "__main__":
    main(sys.argv[1:])
