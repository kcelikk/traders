"""İlk strateji plugin'i: durum × hücre kuralı (Faz 6). Mevcut mantık **sarmalanır, yazılmaz**.

`fbot/core/decision.py:decide_explain` ve `fbot/core/state_engine.py` olduğu gibi kullanılır.
Amaç, plugin soyutlamasının davranışı değiştirmediğini kanıtlamak: aynı girdi, aynı niyet,
aynı `clientOrderId`. Parite testi (`tests/test_golden_orders.py`) bunu kilitliyor.

Kârlılık gösterilmedi (ADR 0010): `allowed_cells` boşken bu strateji hiçbir niyet üretmez.
"""
from __future__ import annotations

from fbot.core.decision import decide_explain
from fbot.strategy.base import StrategyContext


class StateCellStrategy:
    """Parametreleri `DecisionConfig`'ten gelir; manifest yalnız kimlik ve terfi taşır."""

    id = "v1_state_cell"
    version = "1.0"
    required_streams = ("aggTrade", "bookTicker", "markPrice")

    def __init__(self, decision_cfg):
        self.cfg = decision_cfg

    def on_bar(self, ctx: StrategyContext):
        intent, blocked = decide_explain(ctx.view, self.cfg)
        self.last_block = blocked          # neden üretilmediği çağırana açık kalır
        return [intent] if intent is not None else []
