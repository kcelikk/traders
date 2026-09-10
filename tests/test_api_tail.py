"""Büyüyen gzip dosyasını satır satır okuma (recorder Z_SYNC_FLUSH ile yazar)."""
import gzip
import zlib

from fbot.api.tail import GrowingGzipReader


def test_reads_lines_as_file_grows(tmp_path):
    p = tmp_path / "events-x.jsonl.gz"
    f = gzip.open(p, "wb")
    f.write(b'{"q":1}\n{"q":2}\n'); f.flush(zlib.Z_SYNC_FLUSH)
    r = GrowingGzipReader(p)
    assert list(r.read_new()) == [b'{"q":1}\n', b'{"q":2}\n']
    assert list(r.read_new()) == []
    f.write(b'{"q":3}\n{"q":4'); f.flush(zlib.Z_SYNC_FLUSH)
    assert list(r.read_new()) == [b'{"q":3}\n']          # kısmi satır bekletilir
    f.write(b'}\n'); f.close()                            # kapanış: gzip trailer
    assert list(r.read_new()) == [b'{"q":4}\n']
    assert r.finished


def test_start_from_scratch_on_existing_closed_file(tmp_path):
    p = tmp_path / "e.jsonl.gz"
    with gzip.open(p, "wb") as f:
        f.write(b"a\nb\n")
    r = GrowingGzipReader(p)
    assert list(r.read_new()) == [b"a\n", b"b\n"] and r.finished
