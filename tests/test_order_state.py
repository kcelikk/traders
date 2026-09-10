"""Emir durum makinesi (Faz 9): user data akışından tek doğruluk, tekrar bastırma, kısmi dolum birikimi."""
from decimal import Decimal as D

from fbot.core.order_state import OrderBook as OrderTracker, OrderStatus


def upd(cid, x, X, l="0", z="0", L="0", i=1, t=0, n="0"):
    return {"kind": "order_fill" if x == "TRADE" else ("order_ack" if X in ("NEW", "PARTIALLY_FILLED") else "order_done"),
            "client_id": cid, "symbol": "BTCUSDT", "status": X, "price": L, "qty": l, "cum_qty": z,
            "commission": n, "realized_pnl": "0", "t_ms": 1, "order_id": i, "trade_id": t, "reduce_only": False, "is_maker": False}


def test_lifecycle_new_partial_filled():
    tr = OrderTracker()
    assert tr.apply(upd("e1", "NEW", "NEW")).status == OrderStatus.NEW
    o = tr.apply(upd("e1", "TRADE", "PARTIALLY_FILLED", l="0.3", z="0.3", L="100", t=1))
    assert o.status == OrderStatus.PARTIALLY_FILLED and o.filled == D("0.3") and o.avg_price == D("100")
    o = tr.apply(upd("e1", "TRADE", "FILLED", l="0.7", z="1.0", L="110", t=2))
    assert o.status == OrderStatus.FILLED and o.filled == D("1.0")
    assert o.avg_price == (D("100") * D("0.3") + D("110") * D("0.7")) / D("1.0")
    assert o.is_terminal and tr.open_orders() == []


def test_duplicate_trade_is_ignored():
    tr = OrderTracker()
    tr.apply(upd("e1", "NEW", "NEW"))
    tr.apply(upd("e1", "TRADE", "PARTIALLY_FILLED", l="0.5", z="0.5", L="100", t=7))
    o = tr.apply(upd("e1", "TRADE", "PARTIALLY_FILLED", l="0.5", z="0.5", L="100", t=7))   # aynı tradeId
    assert o.filled == D("0.5") and o.dup_trades == 1


def test_out_of_order_update_does_not_regress_state():
    tr = OrderTracker()
    tr.apply(upd("e1", "NEW", "NEW"))
    tr.apply(upd("e1", "TRADE", "FILLED", l="1", z="1", L="100", t=2))
    o = tr.apply(upd("e1", "TRADE", "PARTIALLY_FILLED", l="0.5", z="0.5", L="99", t=1))    # geç gelen eski olay
    assert o.status == OrderStatus.FILLED and o.filled == D("1")


def test_terminal_states():
    tr = OrderTracker()
    for cid, st in (("a", "CANCELED"), ("b", "EXPIRED"), ("c", "EXPIRED_IN_MATCH"), ("d", "REJECTED")):
        tr.apply(upd(cid, "NEW", "NEW"))
        o = tr.apply(upd(cid, "EXPIRED", st))
        assert o.is_terminal, st
    assert tr.stats()["expired_in_match"] == 1
    assert tr.stats()["rejected"] == 1


def test_unknown_client_id_is_tracked_not_dropped():
    """Borsadan gelen bizim üretmediğimiz emir (likidasyon, ADL) da izlenir."""
    tr = OrderTracker()
    o = tr.apply({**upd("autoclose-1", "TRADE", "FILLED", l="1", z="1", L="100", t=1), "liquidation": True})
    assert o.external and tr.stats()["external"] == 1


def test_commission_accumulates():
    tr = OrderTracker()
    tr.apply(upd("e1", "NEW", "NEW"))
    tr.apply(upd("e1", "TRADE", "PARTIALLY_FILLED", l="0.5", z="0.5", L="100", t=1, n="0.02"))
    o = tr.apply(upd("e1", "TRADE", "FILLED", l="0.5", z="1.0", L="100", t=2, n="0.03"))
    assert o.commission == D("0.05")
