"""Büyüyen gzip dosyasını akış halinde okuma (I/O kenarı). Recorder Z_SYNC_FLUSH ile yazar; ham bayt tail'i zlib ile açılır.

Bellek sınırlı: dosya `read_size` parçalar hâlinde okunur ve her parça `max_out` sınırıyla açılır
(sıkıştırma oranı ne olursa olsun tampon sınırlı kalır). Kısmi son satır bir sonraki çağrıya bekletilir.
"""
from __future__ import annotations

import zlib
from pathlib import Path

DEFAULT_READ_SIZE = 1 << 20    # 1 MiB sıkıştırılmış
DEFAULT_MAX_OUT = 1 << 22      # 4 MiB açılmış


class GrowingGzipReader:
    def __init__(self, path: Path, read_size: int = DEFAULT_READ_SIZE, max_out: int = DEFAULT_MAX_OUT):
        self.path = Path(path)
        self.read_size = read_size
        self.max_out = max_out
        self.pos = 0
        self.dec = zlib.decompressobj(wbits=31)
        self.buf = b""
        self.finished = False
        self.max_buf = 0

    def _emit(self, data: bytes):
        self.buf += data
        self.max_buf = max(self.max_buf, len(self.buf))
        parts = self.buf.splitlines(keepends=True)
        if parts and not parts[-1].endswith(b"\n"):
            self.buf = parts.pop()
        else:
            self.buf = b""
        return parts

    def read_new(self):
        """Yeni tam satırları üretir."""
        if self.finished:
            return
        with self.path.open("rb") as f:
            f.seek(self.pos)
            while True:
                chunk = f.read(self.read_size)
                if not chunk:
                    return
                self.pos += len(chunk)
                while chunk:
                    try:
                        out = self.dec.decompress(chunk, self.max_out)
                    except zlib.error:
                        return
                    chunk = self.dec.unconsumed_tail
                    yield from self._emit(out)
                    if self.dec.eof:
                        self.finished = True
                        return
