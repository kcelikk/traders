"""Faz 0 ölçüm çekirdeği testleri. Saf fonksiyonlar; I/O yok."""
import json

import pytest

from scripts.latency_core import (
    percentiles,
    rest_sample,
    summarize,
    ws_lag,
    hour_bucket,
)


# --- percentiles -----------------------------------------------------------

def test_percentiles_empty_returns_none():
    assert percentiles([]) == {"p50": None, "p95": None, "p99": None}


def test_percentiles_single_value():
    assert percentiles([7.0]) == {"p50": 7.0, "p95": 7.0, "p99": 7.0}


def test_percentiles_nearest_rank_is_deterministic():
    vals = list(range(1, 101))  # 1..100
    out = percentiles(vals)
    # nearest-rank: ceil(p/100 * n)
    assert out == {"p50": 50, "p95": 95, "p99": 99}
    # input order must not matter
    assert percentiles(list(reversed(vals))) == out


def test_percentiles_does_not_mutate_input():
    vals = [3, 1, 2]
    percentiles(vals)
    assert vals == [3, 1, 2]


# --- rest_sample -----------------------------------------------------------

def test_rest_sample_skew_uses_midpoint():
    # gönderim 1000, alım 1100 → orta nokta 1050; sunucu 1060 → skew +10
    s = rest_sample(send_wall_ms=1000, recv_wall_ms=1100, server_time_ms=1060)
    assert s["rtt_ms"] == 100
    assert s["skew_ms"] == 10
    assert s["wall_ms"] == 1000


def test_rest_sample_without_server_time():
    s = rest_sample(send_wall_ms=5, recv_wall_ms=9, server_time_ms=None)
    assert s["rtt_ms"] == 4
    assert s["skew_ms"] is None


# --- ws_lag ----------------------------------------------------------------

def test_ws_lag_combined_stream_envelope():
    msg = {"stream": "btcusdt@aggTrade", "data": {"e": "aggTrade", "E": 1000, "T": 995, "s": "BTCUSDT"}}
    out = ws_lag(msg, recv_wall_ms=1030)
    assert out["stream"] == "btcusdt@aggTrade"
    assert out["E"] == 1000 and out["T"] == 995
    assert out["lag_E_ms"] == 30
    assert out["lag_T_ms"] == 35


def test_ws_lag_raw_stream_without_T():
    msg = {"e": "markPriceUpdate", "E": 2000, "s": "BTCUSDT", "p": "1"}
    out = ws_lag(msg, recv_wall_ms=2007)
    assert out["stream"] == "BTCUSDT@markPriceUpdate"
    assert out["lag_E_ms"] == 7
    assert out["lag_T_ms"] is None


def test_ws_lag_markprice_T_is_next_funding_not_event_time():
    msg = {"stream": "btcusdt@markPrice@1s", "data": {"e": "markPriceUpdate", "E": 1000, "T": 99999999, "s": "BTCUSDT"}}
    out = ws_lag(msg, recv_wall_ms=1050)
    assert out["lag_E_ms"] == 50
    assert out["lag_T_ms"] is None


def test_ws_lag_ignores_control_messages():
    assert ws_lag({"result": None, "id": 1}, recv_wall_ms=1) is None
    assert ws_lag({"id": "x", "status": 200, "result": {}}, recv_wall_ms=1) is None


# --- summarize -------------------------------------------------------------

def test_summarize_basic_stats():
    rows = [{"v": 1.0}, {"v": 3.0}, {"v": 2.0}, {"v": None}]
    s = summarize(rows, "v")
    assert s["count"] == 3
    assert s["min"] == 1.0 and s["max"] == 3.0
    assert s["mean"] == 2.0
    assert s["p50"] == 2.0


def test_summarize_empty():
    s = summarize([], "v")
    assert s["count"] == 0 and s["p50"] is None


# --- hour_bucket -----------------------------------------------------------

def test_hour_bucket_is_utc_hour():
    # 2026-09-10T13:00:00Z = 1789045200000 ms
    assert hour_bucket(1789045200000) == "2026-09-10T13"
    assert hour_bucket(1789045200000 + 59 * 60 * 1000) == "2026-09-10T13"
    assert hour_bucket(1789045200000 + 60 * 60 * 1000) == "2026-09-10T14"
