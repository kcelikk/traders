"""Sabitlenmiş davranış baseline'ı.

Mevcut determinizm testi (`test_replay_determinism.py`) yalnız **iki koşu arası eşitliği**
kontrol ediyor: aynı girdi aynı çıktıyı veriyor mu. Sabitlenmiş bir değer olmadığı için,
davranışı değiştiren bir refactor tüm testleri yeşil bırakabiliyordu.

Bu test o boşluğu kapatır. Kırılması bir hata anlamına gelmez; **kasıtsız bir davranış değişikliği**
anlamına gelir. Planlı re-baseline noktalarında (Gate 2.0, Gate 4.1) baseline bilerek güncellenir
ve güncelleme bir ADR ile komut düzeyi diff raporu gerektirir.
"""
import json
from pathlib import Path

import pytest

from fbot.replay.harness import replay

GOLDEN = Path("tests/golden/replay_baseline.json")


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text())


@pytest.mark.golden
def test_replay_hash_matches_the_pinned_baseline(golden):
    r = replay(Path(golden["fixture"]))
    assert r.hash == golden["hash"], (
        "Replay hash'i değişti. Bu kasıtlıysa: ADR yaz, komut düzeyi diff raporu üret "
        "(make determinism-report), sonra tests/golden/replay_baseline.json'u güncelle."
    )


@pytest.mark.golden
def test_command_counts_match_the_pinned_baseline(golden):
    r = replay(Path(golden["fixture"]))
    assert r.events == golden["events"]
    assert r.commands == golden["commands"]
    assert r.by_kind == golden["by_kind"]
    assert r.parse_errors == golden["parse_errors"] == 0


@pytest.mark.golden
def test_sequence_range_matches(golden):
    r = replay(Path(golden["fixture"]))
    assert (r.first_seq, r.last_seq) == (golden["first_seq"], golden["last_seq"])


def test_baseline_file_documents_why_it_exists(golden):
    """Baseline'ı düşünmeden güncellemeyi zorlaştırır."""
    assert "re-baseline" in golden["not"] and "ADR" in golden["not"]
