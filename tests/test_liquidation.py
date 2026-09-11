"""Likidasyon akışından dakikalık büyüklükler.

Binance `forceOrder` semantiği: `S=SELL` bir **long** pozisyonun zorla kapatılmasıdır (zorunlu
satış), `S=BUY` bir **short** pozisyonun kapatılmasıdır. İşareti ters almak yönü ters çevirir,
bu yüzden testle sabitlenmiştir.
"""
from fbot.research.liquidation import liq_per_minute, parse_force_order

M = 60_000


def ev(t_ms, sym, side, qty, price):
    return {"e": "forceOrder", "E": t_ms,
            "o": {"s": sym, "S": side, "q": str(qty), "ap": str(price), "X": "FILLED", "z": str(qty)}}


def test_sell_side_is_a_long_liquidation():
    r = parse_force_order(ev(0, "XUSDT", "SELL", 10, 2.0))
    assert r["side"] == "long" and r["notional"] == 20.0 and r["symbol"] == "XUSDT"


def test_buy_side_is_a_short_liquidation():
    assert parse_force_order(ev(0, "XUSDT", "BUY", 5, 3.0))["side"] == "short"


def test_unfilled_orders_are_skipped():
    e = ev(0, "XUSDT", "SELL", 10, 2.0)
    e["o"]["X"] = "NEW"
    assert parse_force_order(e) is None


def test_filled_quantity_is_preferred_over_ordered_quantity():
    e = ev(0, "XUSDT", "SELL", 10, 2.0)
    e["o"]["z"] = "4"
    assert parse_force_order(e)["notional"] == 8.0


def test_malformed_event_returns_none():
    assert parse_force_order({"e": "forceOrder"}) is None
    assert parse_force_order({"e": "forceOrder", "o": {"s": "X", "S": "SELL", "q": "abc", "ap": "1", "X": "FILLED"}}) is None


def test_minute_aggregation_splits_by_side():
    rows = [parse_force_order(ev(10_000, "X", "SELL", 10, 2.0)),
            parse_force_order(ev(50_000, "X", "SELL", 5, 2.0)),
            parse_force_order(ev(70_000, "X", "BUY", 1, 100.0))]
    per = liq_per_minute(rows)
    assert per[("X", 0)] == {"liq_long_usdt": 30.0, "liq_short_usdt": 0.0, "liq_count": 2}
    assert per[("X", M)] == {"liq_long_usdt": 0.0, "liq_short_usdt": 100.0, "liq_count": 1}


def test_minutes_without_liquidations_are_absent():
    per = liq_per_minute([parse_force_order(ev(0, "X", "SELL", 1, 1.0))])
    assert ("X", M) not in per


def test_extract_reads_a_recording_and_writes_minute_rows(tmp_path):
    import gzip
    import json as js
    from scripts.extract_liquidations import extract

    d = tmp_path / "rec"; d.mkdir()
    lines = [
        js.dumps({"q": 1, "c": "market", "s": "xusdt@forceOrder",
                  "d": {"stream": "xusdt@forceOrder", "data": ev(0, "XUSDT", "SELL", 10, 2.0)}}),
        js.dumps({"q": 2, "c": "market", "s": "xusdt@aggTrade", "d": {"stream": "x", "data": {"e": "aggTrade"}}}),
        js.dumps({"q": 3, "c": "market", "s": "xusdt@forceOrder",
                  "d": {"stream": "xusdt@forceOrder", "data": ev(70_000, "XUSDT", "BUY", 1, 100.0)}}),
    ]
    with gzip.open(d / "events-1.jsonl.gz", "wb") as f:
        f.write(("\n".join(lines) + "\n").encode())
    out = tmp_path / "liq.jsonl"
    rep = extract(d, out)
    assert rep["liquidations"] == 2 and rep["minutes"] == 2 and rep["lines_scanned"] == 3
    got = [js.loads(l) for l in out.read_text().splitlines()]
    assert got[0] == {"symbol": "XUSDT", "start_ms": 0, "liq_long_usdt": 20.0, "liq_short_usdt": 0.0, "liq_count": 1}
    assert got[1]["liq_short_usdt"] == 100.0


def test_open_file_being_written_is_read_up_to_the_last_complete_line(tmp_path):
    """Kayıt dosyası hâlâ yazılıyorsa gzip bitiş işareti yoktur; okuma çökmemeli."""
    import gzip
    import json as js
    from scripts.extract_liquidations import extract

    d = tmp_path / "rec"; d.mkdir()
    good = js.dumps({"q": 1, "d": {"data": ev(0, "XUSDT", "SELL", 10, 2.0)}}) + "\n"
    with gzip.open(d / "events-1.jsonl.gz", "wb") as f:
        f.write(good.encode() * 3)
    raw = (d / "events-1.jsonl.gz").read_bytes()
    (d / "events-2.jsonl.gz").write_bytes(raw[:-4])          # bitiş işareti kesik
    rep = extract(d, tmp_path / "liq.jsonl")
    assert rep["liquidations"] >= 3 and rep["truncated_files"] == 1
