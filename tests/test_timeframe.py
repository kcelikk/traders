"""1 dk barlardan üst zaman dilimi üretimi.

Kurallar: kovalar epoch'a hizalı (borsa mumlarıyla aynı sınır), eksik dakika kovayı bozmaz,
**tamamlanmamış son kova düşürülür** — yoksa henüz kapanmamış mumla sinyal üretilir (look-ahead).
"""
import pytest

from fbot.research.timeframe import aggregate, buckets_needed

M = 60_000


def bar(start_ms, o, h, l, c, v=1.0, bv=0.5, t=3, spread=None):
    return {"symbol": "X", "start_ms": start_ms, "end_ms": start_ms + M, "open": o, "high": h,
            "low": l, "close": c, "volume": v, "buy_volume": bv, "trades": t, "spread_bps": spread}


def test_five_minute_bucket_takes_first_open_last_close_and_extremes():
    src = [bar(i * M, 100 + i, 110 + i, 90 - i, 105 + i) for i in range(5)]
    out = aggregate(src, 5)
    assert len(out) == 1
    b = out[0]
    assert b["open"] == 100 and b["close"] == 109
    assert b["high"] == 114 and b["low"] == 86
    assert b["start_ms"] == 0 and b["end_ms"] == 5 * M


def test_volume_and_trades_are_summed():
    src = [bar(i * M, 100, 101, 99, 100, v=2.0, bv=1.5, t=10) for i in range(5)]
    b = aggregate(src, 5)[0]
    assert b["volume"] == 10.0 and b["buy_volume"] == 7.5 and b["trades"] == 50


def test_buckets_are_aligned_to_the_epoch_not_to_the_first_bar():
    """İlk bar 07:03 ise 5 dk kova 07:00–07:05'tir; 07:03–07:08 değil."""
    start = 3 * M                      # 00:03
    src = [bar(start + i * M, 100, 101, 99, 100) for i in range(7)]   # 00:03 … 00:09
    out = aggregate(src, 5)
    assert [b["start_ms"] for b in out] == [5 * M]      # yalnızca 00:05–00:10 tam dolu
    assert out[0]["end_ms"] == 10 * M


def test_incomplete_trailing_bucket_is_dropped():
    src = [bar(i * M, 100, 101, 99, 100) for i in range(7)]           # 5 tam + 2 eksik
    assert [b["start_ms"] for b in aggregate(src, 5)] == [0]


def test_bucket_with_missing_minutes_is_dropped_not_guessed():
    """Kayıp dakika varsa kova eksiktir; tahmin etmek yerine atlanır."""
    src = [bar(0, 100, 101, 99, 100), bar(M, 100, 101, 99, 100), bar(3 * M, 100, 101, 99, 100),
           bar(4 * M, 100, 101, 99, 100)]                             # 00:02 yok
    assert aggregate(src, 5) == []


def test_one_minute_is_a_passthrough():
    src = [bar(i * M, 100 + i, 101, 99, 100) for i in range(3)]
    assert aggregate(src, 1) == src


def test_spread_is_averaged_over_known_values_only():
    src = [bar(0, 100, 101, 99, 100, spread=2.0), bar(M, 100, 101, 99, 100, spread=None),
           bar(2 * M, 100, 101, 99, 100, spread=4.0), bar(3 * M, 100, 101, 99, 100, spread=None),
           bar(4 * M, 100, 101, 99, 100, spread=None)]
    assert aggregate(src, 5)[0]["spread_bps"] == 3.0
    src2 = [bar(i * M, 100, 101, 99, 100, spread=None) for i in range(5)]
    assert aggregate(src2, 5)[0]["spread_bps"] is None


def test_unsorted_input_is_rejected_rather_than_silently_mixed():
    src = [bar(2 * M, 100, 101, 99, 100), bar(0, 100, 101, 99, 100)]
    with pytest.raises(ValueError):
        aggregate(src, 5)


def test_buckets_needed_translates_window_lengths():
    assert buckets_needed(240, 1) == 240 and buckets_needed(240, 5) == 240
    assert buckets_needed(240, 60) == 240


def test_scan_labels_each_row_with_its_timeframe(tmp_path):
    """Tarama birden çok zaman dilimini birlikte raporlar; her satır hangi dilimden geldiğini taşır."""
    import json
    import random
    from scripts import barrier_scan

    rng = random.Random(3)
    px, rows = 100.0, []
    for i in range(3000):
        px *= 1 + rng.gauss(0, 0.0008)
        rows.append({"symbol": "X", "start_ms": i * M, "end_ms": (i + 1) * M, "open": px,
                     "high": px * 1.001, "low": px * 0.999, "close": px, "volume": 1.0,
                     "buy_volume": 0.5, "trades": 3, "spread_bps": 1.0})
    f = tmp_path / "bars.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    cfg = tmp_path / "research.toml"
    cfg.write_text('[bars]\nbar_ms=60000\n[features]\nW=60\nN_short=5\nN_long=15\n[states]\np_lo=0.2\np_hi=0.8\n'
                   '[horizons]\nminutes=[1]\n[costs]\nscenarios=[{name="taker/taker",fee_in_pct=0.05,fee_out_pct=0.05}]\n'
                   '[sampling]\ndiscovery_frac=0.7\nmin_n=10\n[bootstrap]\nn_boot=40\nseed=1\nalpha=0.05\n')
    out = tmp_path / "out.json"
    barrier_scan.main([str(f), "--config", str(cfg), "--tf", "1,5", "--stride", "7",
                       "--screen-boot", "20", "--top", "2", "--json-out", str(out)])
    d = json.loads(out.read_text())
    assert d["timeframes"] == [1, 5]
    assert {r["tf"] for r in d["rows"]} <= {1, 5}
    assert d["per_tf"][str(5)]["bars"] < d["per_tf"][str(1)]["bars"]


def test_extra_fields_survive_aggregation_with_the_last_value():
    """Funding ve zenginleştirme alanları kaybolursa üst zaman dilimi maliyetsiz görünür."""
    src = []
    for i in range(5):
        b = bar(i * M, 100, 101, 99, 100)
        b.update(funding_rate=0.0001 * (i + 1), next_funding_ms=1000 + i, mark=100.0 + i,
                 book_imb=0.1 * i, open_interest=500 + i, taker_ls_ratio=1.0 + i)
        src.append(b)
    out = aggregate(src, 5)[0]
    assert out["funding_rate"] == 0.0005 and out["next_funding_ms"] == 1004   # kova sonundaki değer
    assert out["book_imb"] == 0.4 and out["open_interest"] == 504 and out["mark"] == 104.0


def test_unknown_extra_fields_are_carried_too():
    src = [dict(bar(i * M, 100, 101, 99, 100), yeni_alan=i) for i in range(5)]
    assert aggregate(src, 5)[0]["yeni_alan"] == 4
