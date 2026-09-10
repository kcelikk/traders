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


def test_reads_in_bounded_chunks_across_boundaries(tmp_path):
    """Büyük dosya belleğe tek seferde açılmaz: sınırlı parça okur, satırlar parça sınırını aşsa da bütün gelir."""
    p = tmp_path / "big.jsonl.gz"
    lines = [b'{"q":%d,"pad":"%s"}\n' % (i, b"x" * 200) for i in range(5000)]
    with gzip.open(p, "wb") as f:
        f.write(b"".join(lines))
    r = GrowingGzipReader(p, read_size=4096, max_out=8192)
    got = list(r.read_new())
    assert got == lines and r.finished
    # tampon: max_out + kısmi satır kadar; toplam açılmış boyutun (≈1 MB) çok altında
    assert r.max_buf < 3 * 8192, f"tampon sınırsız büyümüş: {r.max_buf}"


def test_generator_is_lazy(tmp_path):
    p = tmp_path / "l.jsonl.gz"
    with gzip.open(p, "wb") as f:
        f.write(b"a\nb\nc\n")
    r = GrowingGzipReader(p, read_size=8, max_out=8)
    g = r.read_new()
    assert next(g) == b"a\n"
    assert r.pos <= 64          # tüm dosya okunmadı
    assert list(g) == [b"b\n", b"c\n"]
