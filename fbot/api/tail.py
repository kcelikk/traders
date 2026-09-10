"""Büyüyen gzip dosyasını akış halinde okuma (I/O kenarı). Recorder Z_SYNC_FLUSH ile yazar; ham bayt tail'i zlib ile açılır."""
from __future__ import annotations

import zlib
from pathlib import Path


class GrowingGzipReader:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.pos = 0
        self.dec = zlib.decompressobj(wbits=31)
        self.buf = b""
        self.finished = False

    def read_new(self):
        if self.finished:
            return
        with self.path.open("rb") as f:
            f.seek(self.pos)
            chunk = f.read()
        if not chunk:
            return
        self.pos += len(chunk)
        try:
            self.buf += self.dec.decompress(chunk)
        except zlib.error:
            return
        if self.dec.eof:
            self.finished = True
        # O(n): tampon bir kez bölünür; son parça (satır sonu yoksa) bekletilir
        parts = self.buf.splitlines(keepends=True)
        if parts and not parts[-1].endswith(b"\n"):
            self.buf = parts.pop()
        else:
            self.buf = b""
        yield from parts
