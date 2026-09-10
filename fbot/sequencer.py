"""Tek sıralama noktası (Rule Zero #1). Saf."""
from __future__ import annotations

from fbot.events import RawEvent


class Sequencer:
    __slots__ = ("last_seq",)

    def __init__(self, start: int = 0):
        self.last_seq = start

    def next(self, recv_ns: int, mono_ns: int, cat: str, stream: str, raw: bytes) -> RawEvent:
        self.last_seq += 1
        return RawEvent(self.last_seq, recv_ns, mono_ns, cat, stream, raw)
