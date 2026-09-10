"""Kayıt bütünlük denetimleri. Saf; sayar, fırlatmaz."""
from __future__ import annotations

import json


class SeqChecker:
    def __init__(self):
        self.first = None
        self.last = None
        self.count = 0
        self.gaps = 0
        self.missing = 0
        self.dups = 0

    def feed(self, seq: int):
        self.count += 1
        if self.first is None:
            self.first = seq
        elif seq == self.last:
            self.dups += 1
        elif seq < self.last:
            self.dups += 1
        elif seq > self.last + 1:
            self.gaps += 1
            self.missing += seq - self.last - 1
        self.last = seq if self.last is None or seq > self.last else self.last

    def report(self) -> dict:
        return {"first": self.first, "last": self.last, "count": self.count, "gaps": self.gaps, "missing": self.missing, "dups": self.dups}


def _category_of(stream: str) -> str:
    return "public" if ("bookTicker" in stream or "depth" in stream) else "market"


class StreamChecker:
    """Stream başına: aggTrade `a` ardışık, bookTicker `u` azalmaz, depth `pu == önceki u`, `E` geriye gitmez."""

    def __init__(self):
        self.state: dict[str, dict] = {}

    def _st(self, stream):
        return self.state.setdefault(stream, {"count": 0, "breaks": 0, "E_regressions": 0, "last_id": None, "last_E": None, "parse_errors": 0})

    def reset(self, category: str):
        """Kategori yeniden bağlandı: zincir bilgisi sıfırlanır, kopuş sayılmaz."""
        for stream, st in self.state.items():
            if _category_of(stream) == category:
                st["last_id"] = None

    def feed(self, stream: str, raw: bytes):
        st = self._st(stream)
        st["count"] += 1
        try:
            d = json.loads(raw)
            d = d.get("data", d)
        except ValueError:
            st["parse_errors"] += 1
            return
        e = d.get("e")
        E = d.get("E")
        if E is not None and st["last_E"] is not None and E < st["last_E"]:
            st["E_regressions"] += 1
        if E is not None:
            st["last_E"] = E
        if e == "aggTrade":
            a = d.get("a")
            if st["last_id"] is not None and a != st["last_id"] + 1:
                st["breaks"] += 1
            st["last_id"] = a
        elif e == "bookTicker":
            u = d.get("u")
            if st["last_id"] is not None and u < st["last_id"]:
                st["breaks"] += 1
            st["last_id"] = u if st["last_id"] is None or u >= st["last_id"] else st["last_id"]
        elif e == "depthUpdate":
            if st["last_id"] is not None and d.get("pu") != st["last_id"]:
                st["breaks"] += 1
            st["last_id"] = d.get("u")

    def report(self) -> dict:
        return {s: {k: v for k, v in st.items() if k not in ("last_id", "last_E")} for s, st in self.state.items()}
