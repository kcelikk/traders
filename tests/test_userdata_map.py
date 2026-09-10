import json

from fbot.gateway.userdata_map import map_user_event


def otu(**o):
    base = {"s": "BTCUSDT", "c": "p1-X-v1", "S": "SELL", "o": "MARKET", "f": "GTC", "q": "0.001", "p": "0", "ap": "0", "sp": "0",
            "x": "TRADE", "X": "FILLED", "i": 1, "l": "0.001", "z": "0.001", "L": "78000.5", "N": "USDT", "n": "0.039", "T": 5, "t": 9,
            "m": False, "R": True, "wt": "CONTRACT_PRICE", "ot": "MARKET", "ps": "BOTH", "cp": False, "rp": "1.2", "V": "EXPIRE_TAKER", "er": "0"}
    base.update(o)
    return {"e": "ORDER_TRADE_UPDATE", "E": 6, "T": 5, "o": base}


def test_order_trade_fill_maps_to_order_fill():
    ev = map_user_event(otu())
    assert ev == {"kind": "order_fill", "client_id": "p1-X-v1", "symbol": "BTCUSDT", "price": "78000.5", "qty": "0.001", "cum_qty": "0.001",
                  "status": "FILLED", "reduce_only": True, "is_maker": False, "commission": "0.039", "realized_pnl": "1.2", "t_ms": 5}


def test_order_expired_in_match_and_rejected_map_to_order_done():
    assert map_user_event(otu(x="EXPIRED", X="EXPIRED_IN_MATCH", l="0", z="0"))["kind"] == "order_done"
    assert map_user_event(otu(x="EXPIRED", X="EXPIRED_IN_MATCH", l="0", z="0"))["status"] == "EXPIRED_IN_MATCH"
    assert map_user_event(otu(x="NEW", X="NEW", l="0", z="0"))["kind"] == "order_ack"


def test_liquidation_client_id_is_flagged():
    ev = map_user_event(otu(c="autoclose-123"))
    assert ev["kind"] == "order_fill" and ev["liquidation"] is True


def algo(**o):
    base = {"caid": "p1-SL-v1", "aid": 5, "at": "CONDITIONAL", "o": "STOP_MARKET", "s": "BTCUSDT", "S": "SELL", "ps": "BOTH", "f": "GTC",
            "q": "0", "X": "NEW", "ai": "", "tp": "77000", "cp": True, "wt": "MARK_PRICE", "pP": True, "R": False, "rm": "", "ia": False}
    base.update(o)
    return {"e": "ALGO_UPDATE", "E": 2, "T": 1, "o": base}


def test_algo_status_mapping():
    assert map_user_event(algo())["kind"] == "algo_ack"
    assert map_user_event(algo(X="TRIGGERED", ai="123"))["kind"] == "algo_triggered"
    assert map_user_event(algo(X="TRIGGERING"))["kind"] == "algo_triggering"
    r = map_user_event(algo(X="REJECTED", rm="Reduce Only reject"))
    assert r["kind"] == "algo_rejected" and r["reason"] == "Reduce Only reject"
    assert map_user_event(algo(X="CANCELED"))["kind"] == "algo_canceled"
    assert map_user_event(algo(X="EXPIRED"))["kind"] == "algo_rejected"
    assert map_user_event(algo(X="FINISHED"))["kind"] == "algo_finished"
    assert map_user_event(algo())["client_algo_id"] == "p1-SL-v1"


def test_unknown_event_returns_none():
    assert map_user_event({"e": "MARGIN_CALL"}) is None
    assert map_user_event({"e": "listenKeyExpired"}) == {"kind": "listen_key_expired"}
