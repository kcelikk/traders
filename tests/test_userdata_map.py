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
                  "status": "FILLED", "reduce_only": True, "is_maker": False, "commission": "0.039", "realized_pnl": "1.2", "t_ms": 5,
                  "trade_id": 9, "order_id": 1}


def test_fill_carries_trade_id_and_order_id_for_dedupe():
    """Gate 3b kanıtı: `OrderBook.apply` dedupe için `trade_id` okuyor; eşleyici bunu vermiyordu,
    yani tekrar bastırma sessizce çalışmıyordu."""
    from fbot.core.order_state import OrderBook

    ev = map_user_event(otu(t=42, i=777))
    assert ev["trade_id"] == 42 and ev["order_id"] == 777
    ob = OrderBook()
    ob.apply(ev)
    ob.apply(ev)                        # aynı tradeId ikinci kez
    o = ob.orders["p1-X-v1"]
    assert o.dup_trades == 1 and o.filled == __import__("decimal").Decimal("0.001")
    assert o.order_id == 777


def test_no_trade_means_no_trade_id():
    """Gerçek çerçevede işlem yokken `t` alanı 0 gelir; 0 bir tradeId değildir."""
    ev = map_user_event(otu(x="NEW", X="NEW", t=0, l="0", z="0"))
    assert ev["kind"] == "order_ack" and ev.get("trade_id") is None and ev["order_id"] == 1


def test_trade_lite_is_mapped_but_marked_separately():
    """Gate 0 §2: dokümanda olmayan tip. Yok saymak güvenli ama **bilinçli** olmalı; çift sayılmamalı."""
    ev = map_user_event({"e": "TRADE_LITE", "E": 1, "T": 2, "s": "BTCUSDT", "q": "0.0007", "p": "0.00",
                         "m": False, "c": "t0Labc", "S": "BUY", "L": "77290.70", "l": "0.0007", "t": 536962673, "i": 28581489905})
    assert ev["kind"] == "trade_lite" and ev["trade_id"] == 536962673 and ev["client_id"] == "t0Labc"


def test_account_update_carries_balance_and_position():
    ev = map_user_event({"e": "ACCOUNT_UPDATE", "T": 1, "E": 1,
                         "a": {"B": [{"a": "USDT", "wb": "4208.4", "cw": "4208.4", "bc": "0"}],
                               "P": [{"s": "BTCUSDT", "pa": "0.0007", "ep": "77290.7", "cr": "-61.78",
                                      "up": "-0.008", "mt": "cross", "ps": "BOTH", "bep": "77321.6"}],
                               "m": "ORDER"}})
    assert ev["kind"] == "account_update" and ev["reason"] == "ORDER"
    assert ev["balances"][0]["wallet"] == "4208.4"
    assert ev["positions"][0]["qty"] == "0.0007" and ev["positions"][0]["breakeven"] == "77321.6"


def test_margin_call_and_config_update_are_not_silently_dropped():
    mc = map_user_event({"e": "MARGIN_CALL", "T": 1, "p": [{"s": "BTCUSDT", "pa": "0.1", "mt": "cross", "mm": "1.2", "up": "-5"}]})
    assert mc["kind"] == "margin_call" and mc["positions"][0]["maint_margin"] == "1.2"
    cfg = map_user_event({"e": "ACCOUNT_CONFIG_UPDATE", "T": 1, "ac": {"s": "BTCUSDT", "l": 10}})
    assert cfg["kind"] == "account_config" and cfg["leverage"] == 10


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
    assert map_user_event({"e": "STRATEGY_UPDATE"}) is None
    assert map_user_event({"e": "listenKeyExpired"}) == {"kind": "listen_key_expired"}
