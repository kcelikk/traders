"""Barlara defter dengesizliği ve konumlanma metriklerinin eklenmesi."""
import json
import zipfile
from datetime import datetime, timezone

from scripts.enrich_bars import enrich

M = 60_000
T0 = int(datetime(2026, 9, 1, tzinfo=timezone.utc).timestamp() * 1000)


def zip_with(path, name, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(name, text)


def setup(tmp_path, depth=True, metrics=True):
    hist = tmp_path / "history"
    if depth:
        zip_with(hist / "bookDepth" / "X" / "X-bookDepth-2026-09-01.zip", "d.csv",
                 "timestamp,percentage,depth,notional\n"
                 "2026-09-01 00:00:30,-1.00,10,1000\n2026-09-01 00:00:30,1.00,5,500\n"
                 "2026-09-01 00:01:30,-1.00,1,100\n2026-09-01 00:01:30,1.00,9,900\n")
    if metrics:
        zip_with(hist / "metrics" / "X" / "X-metrics-2026-09-01.zip", "m.csv",
                 "create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
                 "sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n"
                 "2026-09-01 00:00:00,X,100,1000,1.0,2.0,0.9,1.5\n")
    src = tmp_path / "bars.jsonl"
    src.write_text("".join(json.dumps({"symbol": "X", "start_ms": T0 + i * M, "end_ms": T0 + (i + 1) * M,
                                       "open": 100, "high": 101, "low": 99, "close": 100, "volume": 1.0,
                                       "buy_volume": 0.5, "trades": 3, "spread_bps": 1.0}) + "\n"
                                      for i in range(3)))
    return hist, src


def rows_of(path):
    return [json.loads(l) for l in path.read_text().splitlines()]


def test_depth_and_metrics_are_attached_to_matching_minutes(tmp_path):
    hist, src = setup(tmp_path)
    out = tmp_path / "out.jsonl"
    rep = enrich(src, out, hist, band_pct=1.0)
    r = rows_of(out)
    assert round(r[0]["book_imb"], 6) == round(500 / 1500, 6)
    assert round(r[1]["book_imb"], 6) == round(-800 / 1000, 6)
    assert r[0]["depth_usdt"] == 1500.0
    assert r[0]["open_interest"] == 100.0 and r[0]["taker_ls_ratio"] == 1.5
    assert rep["bars"] == 3 and rep["with_depth"] == 2 and rep["with_metrics"] == 3


def test_minutes_without_a_depth_sample_get_null_not_zero(tmp_path):
    hist, src = setup(tmp_path)
    out = tmp_path / "out.jsonl"
    enrich(src, out, hist, band_pct=1.0)
    assert rows_of(out)[2]["book_imb"] is None


def test_missing_archive_files_leave_fields_null(tmp_path):
    hist, src = setup(tmp_path, depth=False, metrics=False)
    out = tmp_path / "out.jsonl"
    rep = enrich(src, out, hist, band_pct=1.0)
    r = rows_of(out)[0]
    assert r["book_imb"] is None and r["open_interest"] is None
    assert rep["with_depth"] == 0 and rep["with_metrics"] == 0


def test_original_bar_fields_are_preserved(tmp_path):
    hist, src = setup(tmp_path)
    out = tmp_path / "out.jsonl"
    enrich(src, out, hist, band_pct=1.0)
    a, b = rows_of(src)[0], rows_of(out)[0]
    assert all(b[k] == v for k, v in a.items())
