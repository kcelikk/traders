"""Saatlik gzip rotasyon + manifest (ADR 0005). I/O kenarı."""
from __future__ import annotations

import gzip
import hashlib
import json
import time
import zlib
from datetime import datetime, timezone
from pathlib import Path

from fbot.events import RawEvent, encode


class RotatingGzipWriter:
    def __init__(self, out_dir: Path, rotate_s: int = 3600):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.rotate_s = rotate_s
        self._f = None
        self._name = None
        self._bucket = None
        self._sha = None
        self._count = 0
        self._bytes = 0
        self._first = None
        self._last = None
        self._manifest = (self.out_dir / "manifest.jsonl").open("a")

    def _bucket_of(self, recv_ns: int) -> int:
        return (recv_ns // 10**9) // self.rotate_s

    def _open(self, ev: RawEvent):
        self._bucket = self._bucket_of(ev.recv_ns)
        ts = datetime.fromtimestamp(self._bucket * self.rotate_s, tz=timezone.utc).strftime("%Y%m%dT%H%M")
        self._name = f"events-{ts}-{ev.seq}.jsonl.gz"
        self._f = gzip.open(self.out_dir / self._name, "wb", compresslevel=6)
        self._sha = hashlib.sha256()
        self._count = 0
        self._bytes = 0
        self._first = ev.seq
        self._last = None

    def _close_current(self):
        if self._f is None:
            return
        self._f.close()
        self._manifest.write(json.dumps({
            "file": self._name, "first_seq": self._first, "last_seq": self._last, "count": self._count,
            "bytes": self._bytes, "sha256": self._sha.hexdigest(), "closed_at_ns": time.time_ns(),
        }) + "\n")
        self._manifest.flush()
        self._f = None

    def write(self, ev: RawEvent):
        if self._f is None or self._bucket_of(ev.recv_ns) != self._bucket:
            self._close_current()
            self._open(ev)
        line = encode(ev)
        self._f.write(line)
        self._sha.update(line)
        self._count += 1
        self._bytes += len(line)
        self._last = ev.seq

    def flush(self):
        if self._f is not None:
            self._f.flush(zlib.Z_SYNC_FLUSH)

    def close(self):
        self._close_current()
        self._manifest.close()

    @property
    def current_file(self) -> str | None:
        return self._name if self._f is not None else None
