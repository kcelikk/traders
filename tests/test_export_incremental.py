"""Artımlı export: dosya dosya ilerleyip state'i taşıyan çıktı, tek seferlik tam export ile bit-eşit olmalı."""
import gzip
import json
from pathlib import Path

from fbot.replay.export import export_bars

FIX = Path("tests/fixtures/rec-mini")


def split_fixture(tmp_path: Path) -> Path:
    src = next(FIX.glob("events-*.jsonl.gz"))
    lines = gzip.open(src, "rb").read().splitlines(keepends=True)
    d = tmp_path / "split"; d.mkdir()
    half = len(lines) // 2
    gzip.open(d / "events-20260910T0800-1.jsonl.gz", "wb").write(b"".join(lines[:half]))
    gzip.open(d / "events-20260910T0800-2.jsonl.gz", "wb").write(b"".join(lines[half:]))
    (d / "manifest.jsonl").write_text("".join(json.dumps({"file": n}) + "\n" for n in ("events-20260910T0800-1.jsonl.gz", "events-20260910T0800-2.jsonl.gz")))
    return d


def test_incremental_equals_full(tmp_path):
    full_out = tmp_path / "full" / "bars.jsonl"
    r_full = export_bars(FIX, full_out)
    d = split_fixture(tmp_path)
    inc_out = tmp_path / "inc" / "bars.jsonl"
    r1 = export_bars(d, inc_out, max_files=1)      # yalnızca ilk dosya
    r2 = export_bars(d, inc_out)                   # ikinci dosya artımlı; ilki cache'ten
    assert r2["files_replayed"] == 1 and r2["files_cached"] == 1
    assert full_out.read_bytes() == inc_out.read_bytes()
    assert r_full["bars"] == r2["bars"] > 0


def test_rerun_without_new_files_replays_nothing(tmp_path):
    out = tmp_path / "bars.jsonl"
    export_bars(FIX, out)
    r = export_bars(FIX, out)
    assert r["files_replayed"] == 0 and r["files_cached"] == 1
