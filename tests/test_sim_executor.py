"""Basit dolum simülatörü (Faz 4 replay karşılaştırması; Faz 7 paper çekirdeği). Saf; seed'li gecikme."""
from decimal import Decimal

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder
from fbot.execution.sim import SimConfig, SimExecutor

MS = 1_000_000
CFG = SimConfig(latency_ms=400, seed=1)


def test_market_reduce_only_fills_at_opposite_side_after_latency():
    sim = SimExecutor(CFG)
    sim.on_book("XUSDT", Decimal("99.9"), Decimal("100.1"), now_ns=0)
    sim.submit(PlaceOrder("XUSDT", "SELL", "MARKET", Decimal("1"), None, True, "p1-X-v1", None), now_ns=0)
    assert sim.poll(now_ns=100 * MS) == []                      # gecikme dolmadı
    sim.on_book("XUSDT", Decimal("99.5"), Decimal("99.7"), now_ns=300 * MS)
    evs = sim.poll(now_ns=500 * MS)
    assert len(evs) == 1 and evs[0]["kind"] == "exit_fill" and evs[0]["price"] == "99.5" and evs[0]["client_id"] == "p1-X-v1"


def test_algo_triggers_on_mark_and_fills_at_opposite_side():
    sim = SimExecutor(CFG)
    sim.submit(PlaceAlgo("XUSDT", "SELL", "STOP_MARKET", Decimal("98"), True, "MARK_PRICE", True, "p1-SL-v1"), now_ns=0)
    acks = sim.poll(now_ns=500 * MS)
    assert acks == [{"kind": "algo_ack", "client_algo_id": "p1-SL-v1", "t_ns": 400 * MS}]
    sim.on_book("XUSDT", Decimal("97.8"), Decimal("98.0"), now_ns=1000 * MS)
    assert sim.on_mark("XUSDT", Decimal("98.5"), now_ns=1000 * MS) == []
    evs = sim.on_mark("XUSDT", Decimal("97.9"), now_ns=2000 * MS)     # tetik
    assert evs[0]["kind"] == "algo_triggered" and evs[0]["client_algo_id"] == "p1-SL-v1"
    fills = sim.poll(now_ns=2500 * MS)
    assert fills and fills[0]["kind"] == "exit_fill" and fills[0]["price"] == "97.8" and fills[0]["reason"] == "sl"


def test_cancel_removes_algo_and_take_profit_triggers_upward():
    sim = SimExecutor(CFG)
    sim.submit(PlaceAlgo("XUSDT", "SELL", "TAKE_PROFIT_MARKET", Decimal("103"), True, "MARK_PRICE", True, "p1-TP-v1"), now_ns=0)
    sim.poll(now_ns=500 * MS)
    sim.submit(CancelAlgo("XUSDT", "p1-TP-v1"), now_ns=600 * MS)
    sim.poll(now_ns=1100 * MS)
    assert sim.on_mark("XUSDT", Decimal("104"), now_ns=1200 * MS) == []      # iptal edilmişti
    sim.submit(PlaceAlgo("XUSDT", "SELL", "TAKE_PROFIT_MARKET", Decimal("103"), True, "MARK_PRICE", True, "p1-TP-v2"), now_ns=1300 * MS)
    sim.poll(now_ns=1800 * MS)
    assert sim.on_mark("XUSDT", Decimal("104"), now_ns=1900 * MS)[0]["client_algo_id"] == "p1-TP-v2"


def test_entry_intent_fills_taker_at_ask():
    sim = SimExecutor(CFG)
    sim.on_book("XUSDT", Decimal("99.9"), Decimal("100.1"), now_ns=0)
    sim.submit(PlaceOrder("XUSDT", "BUY", "MARKET", Decimal("1"), None, False, "e1", None), now_ns=0)
    evs = sim.poll(now_ns=500 * MS)
    assert evs[0]["kind"] == "entry_fill_price" and evs[0]["price"] == "100.1"
