import gzip
import hashlib
import json

from fbot.events import RawEvent, decode, encode
from fbot.recorder.writer import RotatingGzipWriter


def ev(seq, hour_ns):
    return RawEvent(seq=seq, recv_ns=hour_ns, mono_ns=seq, cat="market", stream="x@aggTrade", raw=b'{"a":%d}' % seq)


def test_rotation_by_hour_and_manifest_integrity(tmp_path):
    H = 3600 * 10**9
    w = RotatingGzipWriter(tmp_path, rotate_s=3600)
    lines = []
    for seq in range(1, 6):
        e = ev(seq, 1789020000 * 10**9 + (0 if seq <= 3 else H))  # 3 olay ilk saat, 2 olay sonraki
        lines.append(encode(e)); w.write(e)
    w.close()
    manifest = [json.loads(l) for l in (tmp_path / "manifest.jsonl").read_text().splitlines()]
    assert len(manifest) == 2
    assert [m["count"] for m in manifest] == [3, 2]
    assert manifest[0]["first_seq"] == 1 and manifest[0]["last_seq"] == 3
    assert manifest[1]["first_seq"] == 4 and manifest[1]["last_seq"] == 5
    for m in manifest:
        data = gzip.decompress((tmp_path / m["file"]).read_bytes())
        assert hashlib.sha256(data).hexdigest() == m["sha256"]
        assert m["bytes"] == len(data)
        evs = [decode(l + b"\n") for l in data.splitlines()]
        assert [e.seq for e in evs] == list(range(m["first_seq"], m["last_seq"] + 1))


def test_flush_makes_data_readable_before_close(tmp_path):
    w = RotatingGzipWriter(tmp_path, rotate_s=3600)
    w.write(ev(1, 1789020000 * 10**9))
    w.flush()
    files = list(tmp_path.glob("events-*.jsonl.gz"))
    assert len(files) == 1
    # gzip akışı flush sonrası kısmi okunabilir olmalı (Z_SYNC_FLUSH)
    with gzip.open(files[0], "rb") as f:
        assert f.readline().startswith(b'{"q":1,')
    w.close()
