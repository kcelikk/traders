"""Sıcak yol performans regresyon kapısı.

Mikro-benchmark gürültülüdür, bu yüzden eşik geniş: baseline p99'un 3 katı. Amaç küçük
dalgalanmaları yakalamak değil, **büyüklük sırası** bozulmalarını yakalamak (örneğin hot path'e
senkron I/O ya da tam defter sıralaması sızması).
"""
import json
from pathlib import Path

import pytest

from scripts.bench_core import bench

BASELINE = Path("tests/golden/bench_baseline.json")
TOLERANS = 3.0


@pytest.mark.slow
def test_engine_step_p99_has_not_regressed_by_an_order_of_magnitude():
    if not BASELINE.exists():
        pytest.skip("baseline yok: python -m scripts.bench_core --json-out tests/golden/bench_baseline.json")
    base = json.loads(BASELINE.read_text())
    now = bench(Path(base["fixture"]))
    b, n = base["overall"]["p99_us"], now["overall"]["p99_us"]
    assert n <= b * TOLERANS, f"Engine.step p99 {b:.1f} µs → {n:.1f} µs (tolerans ×{TOLERANS})"


@pytest.mark.slow
def test_hot_event_types_are_still_microseconds():
    """aggTrade ve bookTicker sıcak yolun büyük kısmı; milisaniyeye çıkmaları yapısal bir sorundur."""
    now = bench(Path("tests/fixtures/rec-mini"))
    for kind in ("aggTrade", "bookTicker"):
        assert now["by_kind"][kind]["p99_us"] < 1000, f"{kind} p99 {now['by_kind'][kind]['p99_us']} µs"
