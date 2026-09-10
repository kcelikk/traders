"""Local order book — Binance dokümanındaki 9 adım (docs/binance-api-verification.md §11)."""
from decimal import Decimal

from fbot.orderbook import LocalOrderBook


def snap(last_id, bids, asks):
    return {"lastUpdateId": last_id, "bids": bids, "asks": asks}


def diff(U, u, pu, b=(), a=()):
    return {"e": "depthUpdate", "U": U, "u": u, "pu": pu, "b": list(b), "a": list(a)}


def test_buffer_before_snapshot_then_drop_old_and_apply_first_valid():
    ob = LocalOrderBook()
    assert ob.feed(diff(90, 95, 89)) == "buffered"
    assert ob.feed(diff(96, 101, 95, b=[["100.0", "1"]])) == "buffered"
    assert ob.feed(diff(102, 104, 101, a=[["101.0", "2"]])) == "buffered"
    out = ob.apply_snapshot(snap(100, [["99.0", "5"]], [["102.0", "5"]]))
    # u=95 < 100 → drop; U=96<=100<=101 → ilk geçerli; 102..104 pu=101 → uygula
    assert out == ["dropped", "applied", "applied"]
    assert ob.synced and ob.last_u == 104
    assert ob.best_bid() == (Decimal("100.0"), Decimal("1"))
    assert ob.best_ask() == (Decimal("101.0"), Decimal("2"))


def test_first_event_gap_means_snapshot_too_old():
    ob = LocalOrderBook()
    ob.feed(diff(150, 160, 149))
    out = ob.apply_snapshot(snap(100, [], []))
    assert out == ["resync"]
    assert not ob.synced


def test_pu_chain_break_forces_resync_and_rebuffers():
    ob = LocalOrderBook()
    ob.apply_snapshot(snap(10, [["1.0", "1"]], [["2.0", "1"]]))
    assert ob.feed(diff(10, 12, 9)) == "applied"
    assert ob.feed(diff(15, 16, 14)) == "resync"   # pu 14 != 12
    assert not ob.synced
    assert ob.feed(diff(17, 18, 16)) == "buffered"
    assert ob.resyncs == 1


def test_zero_quantity_removes_and_missing_level_removal_is_ok():
    ob = LocalOrderBook()
    ob.apply_snapshot(snap(10, [["1.0", "1"], ["0.9", "2"]], [["2.0", "1"]]))
    assert ob.feed(diff(10, 11, 9, b=[["1.0", "0"], ["5.5", "0"]], a=[["2.0", "3"]])) == "applied"
    assert ob.best_bid() == (Decimal("0.9"), Decimal("2"))
    assert ob.best_ask() == (Decimal("2.0"), Decimal("3"))


def test_absolute_quantity_semantics_and_best_ordering():
    ob = LocalOrderBook()
    ob.apply_snapshot(snap(1, [["10", "1"], ["11", "1"]], [["12", "1"], ["13", "1"]]))
    ob.feed(diff(1, 2, 0, b=[["11", "7"]], a=[["12", "9"]]))
    assert ob.best_bid() == (Decimal("11"), Decimal("7"))
    assert ob.best_ask() == (Decimal("12"), Decimal("9"))
    assert ob.top_matches("11", "12") is True
    assert ob.top_matches("10", "12") is False


def test_resync_reasons_are_classified():
    ob = LocalOrderBook()
    ob.apply_snapshot(snap(100, [], []))
    assert ob.feed(diff(101, 103, 100)) == "resync"          # U = lastUpdateId+1 → 'adjacent'
    ob.apply_snapshot(snap(200, [], []))
    assert ob.feed(diff(250, 251, 249)) == "resync"          # gerçek boşluk → 'gap'
    ob.apply_snapshot(snap(300, [], []))
    assert ob.feed(diff(300, 301, 299)) == "applied"
    assert ob.feed(diff(305, 306, 304)) == "resync"          # pu != 301 → 'pu'
    assert ob.resync_reasons == {"adjacent": 1, "gap": 1, "pu": 1}
    assert ob.syncs == 1


def test_compare_snapshot_counts_equal_levels():
    ob = LocalOrderBook()
    ob.apply_snapshot(snap(1, [["10", "1"], ["9", "2"]], [["11", "1"], ["12", "2"]]))
    ob.feed(diff(1, 2, 0, b=[["9", "5"]]))  # local: 9 → 5
    r = ob.compare_snapshot(snap(2, [["10", "1"], ["9", "2"]], [["11", "1"], ["12", "2"]]))
    assert r == {"levels": 4, "equal": 3, "local_extra": 0}
