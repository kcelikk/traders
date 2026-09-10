"""Defter yürüyüşlü dolum simülatörü (ADR 0013). Kurallar: NautilusTrader ve Hummingbot dokümanlarından doğrulandı."""
from decimal import Decimal as D

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder
from fbot.execution.sim import SimConfig, SimExecutor

MS = 1_000_000
CFG = SimConfig(latency_ms=400, seed=1, jitter_ms=0)


def book(sim, sym="X", bids=((99.9, 5),), asks=((100.1, 5),), now=0):
    sim.on_depth(sym, [(D(str(p)), D(str(q))) for p, q in bids], [(D(str(p)), D(str(q))) for p, q in asks], now)


def test_market_buy_walks_book_weighted_average():
    sim = SimExecutor(CFG)
    book(sim, asks=((100.0, 1), (100.5, 1), (101.0, 10)))
    sim.submit(PlaceOrder("X", "BUY", "MARKET", D("1.5"), None, False, "e1", None), 0)
    ev = sim.poll(500 * MS)
    assert len(ev) == 1 and ev[0]["kind"] == "entry_fill_price"
    # 1 @100.0 + 0.5 @100.5 → ort = 100.5/1.5... = (100 + 50.25)/1.5
    assert D(ev[0]["price"]) == (D("100.0") * 1 + D("100.5") * D("0.5")) / D("1.5")
    assert D(ev[0]["qty"]) == D("1.5")


def test_partial_fill_when_depth_insufficient_then_completes():
    sim = SimExecutor(CFG)
    book(sim, asks=((100.0, 1),))
    sim.submit(PlaceOrder("X", "BUY", "MARKET", D("3"), None, False, "e1", None), 0)
    ev = sim.poll(500 * MS)
    assert D(ev[0]["qty"]) == D("1") and ev[0]["partial"] is True
    book(sim, asks=((100.2, 5),), now=600 * MS)          # derinlik geldi
    ev2 = sim.poll(700 * MS)
    assert D(ev2[0]["qty"]) == D("2") and ev2[0]["partial"] is False


def test_partial_timeout_cancels_remainder():
    sim = SimExecutor(SimConfig(latency_ms=400, seed=1, jitter_ms=0, partial_timeout_ms=1000))
    book(sim, asks=((100.0, 1),))
    sim.submit(PlaceOrder("X", "BUY", "MARKET", D("3"), None, False, "e1", None), 0)
    sim.poll(500 * MS)
    ev = sim.poll(2000 * MS)
    assert any(e["kind"] == "order_expired" and e["client_id"] == "e1" for e in ev)
    assert not sim.pending_orders


def test_no_book_means_no_fill_not_best_price():
    sim = SimExecutor(CFG)
    sim.submit(PlaceOrder("X", "BUY", "MARKET", D("1"), None, False, "e1", None), 0)
    assert sim.poll(500 * MS) == []          # eski davranış: en iyi fiyattan doldururdu
    book(sim, asks=((100.0, 5),), now=600 * MS)
    assert sim.poll(700 * MS)[0]["kind"] == "entry_fill_price"


def test_algo_triggers_on_mark_then_walks_book():
    sim = SimExecutor(CFG)
    book(sim, bids=((97.9, 0.5), (97.5, 10)))
    sim.submit(PlaceAlgo("X", "SELL", "STOP_MARKET", D("98"), True, "MARK_PRICE", True, "p1-SL-v1"), 0)
    assert sim.poll(500 * MS)[0]["kind"] == "algo_ack"
    sim.set_position("p1", "X", D("2"))
    assert sim.on_mark("X", D("98.5"), 600 * MS) == []
    trig = sim.on_mark("X", D("97.95"), 700 * MS)
    assert trig[0]["kind"] == "algo_triggered"
    fills = sim.poll(1200 * MS)
    f = next(x for x in fills if x["kind"] == "exit_fill")
    assert D(f["price"]) == (D("97.9") * D("0.5") + D("97.5") * D("1.5")) / D("2")   # defter yürüdü
    assert f["reason"] == "sl"


def test_maker_limit_fills_only_when_market_crosses():
    sim = SimExecutor(CFG)
    book(sim, bids=((99.0, 5),), asks=((99.5, 5),))
    sim.submit(PlaceOrder("X", "BUY", "LIMIT", D("1"), D("99.0"), False, "m1", "GTX"), 0)
    sim.poll(500 * MS)
    book(sim, bids=((98.9, 5),), asks=((99.0, 5),), now=600 * MS)   # dokunma (ask == limit)
    assert not [e for e in sim.poll(700 * MS) if e["kind"] == "entry_fill_price"]
    book(sim, bids=((98.5, 5),), asks=((98.9, 5),), now=800 * MS)   # geçiş (ask < limit)
    ev = [e for e in sim.poll(900 * MS) if e["kind"] == "entry_fill_price"]
    assert ev and D(ev[0]["price"]) == D("99.0")                     # maker: limit fiyatı


def test_latency_jitter_is_seeded_and_repeatable():
    def run(seed):
        sim = SimExecutor(SimConfig(latency_ms=400, seed=seed, jitter_ms=200))
        out = []
        for i in range(6):
            book(sim, asks=((100.0, 10),), now=i * 1000 * MS)
            sim.submit(PlaceOrder("X", "BUY", "MARKET", D("1"), None, False, f"e{i}", None), i * 1000 * MS)
            out += [(e["client_id"], e["ready_ns"]) for e in sim.poll((i + 1) * 1000 * MS)]
        return out
    assert run(7) == run(7)
    assert run(7) != run(8)
    # ready_ns = gönderim + gecikme; jitter [0, 200] ms → [400, 600] ms
    assert all(400 * MS <= r - int(c[1:]) * 1000 * MS <= 600 * MS for c, r in run(7))


def test_cancel_algo_removes_it():
    sim = SimExecutor(CFG)
    book(sim)
    sim.submit(PlaceAlgo("X", "SELL", "TAKE_PROFIT_MARKET", D("103"), True, "MARK_PRICE", True, "p1-TP-v1"), 0)
    sim.poll(500 * MS)
    sim.submit(CancelAlgo("X", "p1-TP-v1"), 600 * MS)
    sim.poll(1100 * MS)
    assert sim.on_mark("X", D("104"), 1200 * MS) == []
