"""Rule Zero kapı testi: aynı fixture iki ayrı process'te → aynı hash; tek bayt değişince hash değişir."""
import gzip
import json
import subprocess
import sys
from pathlib import Path

from fbot.replay.harness import replay

FIX = Path("tests/fixtures/rec-mini")
PY = sys.executable


def run_cli(run_dir: Path) -> dict:
    out = subprocess.check_output([PY, "-m", "scripts.replay", str(run_dir), "--json"], timeout=600)
    return json.loads(out)


def test_two_processes_produce_identical_hash():
    a, b = run_cli(FIX), run_cli(FIX)
    assert a["hash"] == b["hash"]
    assert a["events"] == b["events"] > 1000
    assert a["commands"] > 0 and a["commands"] == b["commands"]


def test_in_process_matches_cli():
    r = replay(FIX)
    assert r.hash == run_cli(FIX)["hash"]


def test_single_byte_change_alters_hash(tmp_path):
    src = next(FIX.glob("events-*.jsonl.gz"))
    lines = gzip.open(src, "rb").read().splitlines(keepends=True)
    # ilk aggTrade satırında miktarın bir basamağını değiştir (hacim bara girer; fiyat bar aralığı içinde kalabilir)
    for i, l in enumerate(lines):
        if b'"c":"market"' in l[:200] and b"@aggTrade" in l[:200]:
            j = l.find(b'"q":"')
            assert j > 0
            k = l.find(b'"', j + 5)
            digits = l[j + 5:k]
            new = digits[:-1] + (b"1" if digits[-1:] != b"1" else b"2")
            lines[i] = l[:j + 5] + new + l[k:]
            break
    d = tmp_path / "mut"; d.mkdir()
    gzip.open(d / src.name, "wb").write(b"".join(lines))
    assert replay(d).hash != replay(FIX).hash
