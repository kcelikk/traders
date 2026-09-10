"""Mantıksal saat (Rule Zero #2). Saf: sistem saati burada okunmaz.
Canlı saat (WallClock) I/O kenarındadır: fbot/gateway/wallclock.py"""
from __future__ import annotations

from typing import Protocol


class Clock(Protocol):
    def now_ns(self) -> int: ...


class ReplayClock:
    """Event alım zamanıyla ilerletilir; geriye gitmez (sıra dışı damgalarda monotonluk korunur)."""
    __slots__ = ("_now",)

    def __init__(self, start_ns: int = 0):
        self._now = start_ns

    def set(self, ns: int) -> None:
        if ns > self._now:
            self._now = ns

    def now_ns(self) -> int:
        return self._now
