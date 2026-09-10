"""Ham olay modeli. Saf: I/O yok, saat yok.

Satır formatı (ADR 0005): {"q":seq,"r":recv_ns,"m":mono_ns,"c":cat,"s":stream,"d":<ham çerçeve>}\n
Ham çerçeve yeniden serileştirilmez; bayt-bayt korunur.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RawEvent:
    seq: int
    recv_ns: int
    mono_ns: int
    cat: str
    stream: str
    raw: bytes


_HEAD = b'{"q":%d,"r":%d,"m":%d,"c":%s,"s":%s,"d":'


def encode(ev: RawEvent) -> bytes:
    head = _HEAD % (ev.seq, ev.recv_ns, ev.mono_ns, json.dumps(ev.cat).encode(), json.dumps(ev.stream).encode())
    return head + ev.raw + b"}\n"


def decode(line: bytes) -> RawEvent:
    """Başlık alanları sabit sırada; 'd' alanı kalan baytlardır (yeniden parse edilmez)."""
    marker = b',"d":'
    i = line.find(marker)
    if i < 0 or not line.startswith(b'{"q":'):
        raise ValueError("malformed event line")
    try:
        head = json.loads((line[:i] + b"}").decode())
    except json.JSONDecodeError as e:
        raise ValueError("malformed event header") from e
    end = line.rstrip(b"\n")
    if not end.endswith(b"}"):
        raise ValueError("malformed event tail")
    raw = end[i + len(marker):-1]
    try:
        return RawEvent(seq=head["q"], recv_ns=head["r"], mono_ns=head["m"], cat=head["c"], stream=head["s"], raw=raw)
    except KeyError as e:
        raise ValueError(f"missing header field {e}") from e


def stream_of(raw: bytes) -> str | None:
    """Birleşik stream çerçevesinden stream adı. Kontrol cevaplarında None."""
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    if isinstance(d, dict):
        s = d.get("stream")
        if isinstance(s, str):
            return s
    return None
