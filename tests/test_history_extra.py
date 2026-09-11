"""Arşivden gelen iki yeni veri kaynağı: defter derinliği ve pozisyon metrikleri.

İkisi de 1 dakikalık barlara hizalanır. Hizalama kuralı: bir bara yalnızca **o barın kapanışına
kadar** yayınlanmış değerler girer. Sonraki değeri kullanmak look-ahead olur.
"""
import pytest

from fbot.research.bookdepth import parse_book_depth, imbalance_per_minute
from fbot.research.metrics import parse_metrics, metrics_per_minute

M = 60_000


def base_ms(day="2026-09-01"):
    from datetime import datetime, timezone
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp() * 1000)


T0 = base_ms()
DEPTH_CSV = """timestamp,percentage,depth,notional
2026-09-01 00:00:04,-1.00,10.0,1000.0
2026-09-01 00:00:04,1.00,5.0,500.0
2026-09-01 00:00:04,-5.00,40.0,4000.0
2026-09-01 00:00:04,5.00,20.0,2000.0
2026-09-01 00:01:07,-1.00,2.0,200.0
2026-09-01 00:01:07,1.00,8.0,800.0
"""
METRICS_CSV = """create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio
2026-09-01 00:00:00,BTCUSDT,100.0,1000000.0,1.05,2.09,0.99,2.31
2026-09-01 00:15:00,BTCUSDT,110.0,1100000.0,1.10,2.20,1.01,1.90
"""


def test_book_depth_rows_are_parsed_with_signed_percentage():
    rows = parse_book_depth(DEPTH_CSV)
    assert len(rows) == 6
    assert rows[0]["pct"] == -1.0 and rows[0]["notional"] == 1000.0
    assert rows[0]["t_ms"] % 1000 == 0


def test_imbalance_is_bid_minus_ask_over_total_at_one_percent():
    per = imbalance_per_minute(parse_book_depth(DEPTH_CSV), band_pct=1.0)
    # 00:00 → alış 1000, satış 500 → (1000-500)/1500
    assert round(per[T0]["imb"], 6) == round(500 / 1500, 6)
    # 00:01 → alış 200, satış 800
    assert round(per[T0 + M]["imb"], 6) == round(-600 / 1000, 6)


def test_wider_band_includes_the_outer_levels():
    per = imbalance_per_minute(parse_book_depth(DEPTH_CSV), band_pct=5.0)
    assert round(per[T0]["imb"], 6) == round((1000 + 4000 - 500 - 2000) / 7500, 6)
    assert per[T0]["depth_usdt"] == 7500.0


def test_minute_with_no_sample_is_absent_not_zero():
    per = imbalance_per_minute(parse_book_depth(DEPTH_CSV), band_pct=1.0)
    assert T0 + 2 * M not in per


def test_metrics_rows_are_parsed():
    rows = parse_metrics(METRICS_CSV)
    assert len(rows) == 2 and rows[0]["open_interest"] == 100.0
    assert rows[1]["taker_ls_ratio"] == 1.90


def test_metrics_are_carried_forward_but_never_backward():
    per = metrics_per_minute(parse_metrics(METRICS_CSV), until_ms=T0 + 20 * M)
    assert per[T0]["open_interest"] == 100.0
    assert per[T0 + 14 * M]["open_interest"] == 100.0      # 00:15'e kadar eski değer
    assert per[T0 + 15 * M]["open_interest"] == 110.0
    assert per[T0 + 16 * M]["open_interest"] == 110.0


def test_minutes_before_the_first_sample_are_absent():
    rows = parse_metrics(METRICS_CSV)
    rows[0]["t_ms"] = T0 + 5 * M
    per = metrics_per_minute(rows[:1], until_ms=T0 + 10 * M)
    assert T0 + 4 * M not in per and per[T0 + 5 * M]["open_interest"] == 100.0


def test_bad_rows_are_skipped_not_fatal():
    assert parse_book_depth("timestamp,percentage,depth,notional\nbozuk\n,,,\n") == []
    assert parse_metrics("create_time,symbol\nbozuk\n") == []


@pytest.mark.parametrize("kind,expected", [
    ("aggTrades", "aggTrades/BTCUSDT/BTCUSDT-aggTrades-2026-09-01.zip"),
    ("bookDepth", "bookDepth/BTCUSDT/BTCUSDT-bookDepth-2026-09-01.zip"),
    ("metrics", "metrics/BTCUSDT/BTCUSDT-metrics-2026-09-01.zip"),
    ("markPriceKlines", "markPriceKlines/BTCUSDT/1m/BTCUSDT-1m-2026-09-01.zip"),
])
def test_archive_url_layout_differs_per_kind(kind, expected):
    """bookDepth ve metrics'te zaman dilimi klasörü yok; kline türlerinde var."""
    from scripts.fetch_history import url_for
    assert url_for(kind, "BTCUSDT", "2026-09-01").endswith(expected)
