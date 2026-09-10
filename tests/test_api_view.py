import json
from decimal import Decimal

from fbot.api.live_view import LiveView, parse_phase_table
from fbot.events import RawEvent

PHASE = """
| Faz | Konu | Durum | Kapı |
|---|---|---|---|
| 0 | Ölçüm | **KAPANDI** 2026-09-10 (x) | y |
| 1 | Kayıt | **KAPANDI** 2026-09-10 | y |
| 4 | Pozisyon | **AKTİF** (2026-09-10) | y |
| 5 | Risk | bekliyor (tasarım notu) | y |
"""


def test_parse_phase_table():
    ph = parse_phase_table(PHASE)
    assert [(p["n"], p["status"]) for p in ph] == [(0, "done"), (1, "done"), (4, "active"), (5, "pending")]


def frame(seq, t, stream, data, cat="market"):
    return RawEvent(seq, t, seq, cat, stream, json.dumps({"stream": stream, "data": data}).encode())


def test_live_view_tracks_market_stats_and_feed():
    v = LiveView(symbols=["BTCUSDT"], W=3, N_short=1, N_long=2)
    t = 10**12
    v.feed(RawEvent(1, t, 1, "ctrl", "run_start", json.dumps({"run_id": "r", "restart_no": 0, "git_sha": "abc"}).encode()))
    v.feed(RawEvent(2, t, 2, "ctrl", "connect", json.dumps({"cat": "public", "n": 1}).encode()))
    v.feed(frame(3, t, "btcusdt@bookTicker", {"e": "bookTicker", "s": "BTCUSDT", "u": 1, "b": "100", "B": "1", "a": "100.1", "A": "1", "E": 1}, cat="public"))
    v.feed(frame(4, t, "btcusdt@markPrice@1s", {"e": "markPriceUpdate", "s": "BTCUSDT", "p": "100.05", "r": "0.0001", "T": 99, "E": 1}))
    for i in range(1, 8):
        v.feed(frame(4 + i, t + i, "btcusdt@aggTrade", {"e": "aggTrade", "s": "BTCUSDT", "a": i, "p": str(100 + i), "q": "1", "T": i * 60_000, "E": 1, "m": False}))
    v.feed(RawEvent(20, t + 20, 20, "ctrl", "stats", json.dumps({"loop_lag_ms": {"p50": 1, "p99": 4.2, "max": 9.0, "n": 100}, "queue": 3, "dropped": 0, "seq": 20, "frames": {"public": 1, "market": 8}, "connects": {"public": 1}, "file": "f"}).encode()))
    s = v.snapshot(now_ns=t + 2_000_000_000)
    u = s["universe"][0]
    assert u["sym"] == "BTCUSDT" and u["price"] == "100.1" and u["mark"] == "100.05" and abs(u["spread_bps"] - 9.99) < 0.1
    assert u["state"] in ("S0", "S1", "S2", "S3", "S4") and u["bars"] >= 5
    assert s["recorder"]["loop_lag_p99"] == 4.2 and s["recorder"]["queue"] == 3 and s["recorder"]["run_id"] == "r"
    assert s["stale"]["public"] >= 1.9 and s["stale"]["market"] >= 1.9
    assert any(f["kind"] == "CONNECT" for f in s["feed"])
    assert len(s["bars"]["BTCUSDT"]) >= 5 and s["bars"]["BTCUSDT"][-1]["c"] > 0
