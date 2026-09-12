"""Parite kontrolü (Gate 5 çıkış koşulu): plugin yolu ile gömülü mantık **bit-eşit** olmalı.

Soyutlama davranışı değiştirmemelidir. Aynı senaryoda iki yol karşılaştırılır:

  A) gömülü: `fbot/core/decision.py:decide_explain` doğrudan
  B) plugin : `fbot/strategy/v1_state_cell.py` → registry → aynı fonksiyon

Fark **bug**'dır, re-baseline değil. Betik farklıysa hata koduyla çıkar.

Kullanım:
    python -m scripts.parity_check                       # sentetik senaryo (tests/scenario.py)
    python -m scripts.parity_check --run data/recordings/testnet --max-files 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from fbot.core.commands import canonical, is_shadow
from fbot.strategy.base import StrategyContext
from fbot.strategy.manifest import parse_manifest
from fbot.strategy.registry import StrategyRegistry
from fbot.strategy.v1_state_cell import StateCellStrategy


def _hash(items) -> str:
    h = hashlib.sha256()
    for x in items:
        h.update(x)
        h.update(b"\n")
    return h.hexdigest()


def registry_for(decision_cfg) -> StrategyRegistry:
    reg = StrategyRegistry(mode="replay")
    strat = StateCellStrategy(decision_cfg)
    reg.register(parse_manifest({"id": strat.id, "version": strat.version,
                                 "allowed_modes": ["replay", "paper"], "promotion_state": "replay_ok"}),
                 strat, code_hash="parity")
    if not reg.active():
        raise SystemExit(f"strateji kayıt defterinde aktif değil: {reg.blocked}")
    return reg


def scenario_parity() -> dict:
    """Aynı senaryo iki kez koşar: gömülü karar motoruyla ve registry üzerinden plugin ile.
    Karşılaştırılan şey niyet değil, **çekirdeğin ürettiği komut dizisidir** — soyutlama zincirin
    hiçbir halkasını değiştirmemeli."""
    from tests.scenario import core_cfg, discovered_cells, live_run

    cells = discovered_cells()
    embedded_cfg = core_cfg(cells)
    _, trader_a = live_run(cells)
    a = [canonical(c) for c in trader_a.commands if not is_shadow(c)]

    plugin_cfg = type(embedded_cfg)(**{**embedded_cfg.__dict__, "strategies": registry_for(embedded_cfg.decision)})
    _, trader_b = live_run(cells, cfg=plugin_cfg)
    b = [canonical(c) for c in trader_b.commands if not is_shadow(c)]

    return {"gomulu": {"hash": _hash(a), "komut": len(a)},
            "plugin": {"hash": _hash(b), "komut": len(b)},
            "esit": a == b,
            "ilk_fark": next((i for i, (x, y) in enumerate(zip(a, b)) if x != y), None)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    r = scenario_parity()
    text = json.dumps(r, ensure_ascii=False, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")
    return 0 if r["esit"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
