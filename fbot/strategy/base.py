"""Strateji sözleşmesi. **Saf**: I/O yok, saat okumaz, emir göndermez.

Strateji yalnız **niyet** üretir. Niyetin emre dönüşmesi risk motorundan (K1–K18) ve emir
yolundan geçer; strateji bu katmanları atlayamaz. Bu ayrım yeni değil — bugünkü
`fbot/core/decision.py` da niyet üretiyor — Gate 5 onu **çoğullaştırıyor**.

Determinizm: `on_bar` girdisi tamamen `StrategyContext`'ten gelir. Saat, rastlantı, dosya ve ağ
yoktur; aynı bağlam aynı niyeti üretir (`tests/test_purity.py` bu paketi tarar).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

MODES = ("replay", "paper", "testnet", "live")
PROMOTION = ("draft", "replay_ok", "paper_ok", "testnet_ok", "live")


@dataclass(frozen=True)
class StrategyContext:
    """Stratejinin gördüğü her şey. `view` mevcut karar motorunun girdi sözlüğüdür (aynı alanlar)."""
    symbol: str
    view: dict
    now_ns: int
    params: dict


@runtime_checkable
class Strategy(Protocol):
    id: str
    version: str
    required_streams: tuple

    def on_bar(self, ctx: StrategyContext):
        """Bar kapanışında niyet listesi döndürür (`EntryIntent`). Boş liste normaldir."""
