"""Emir gönderim kuyruğu (Gate 2.1): HTTP döngüyü tutmaz, sıkışıklıkta önce giriş feda edilir."""
import asyncio
import time
from decimal import Decimal as D

import pytest

from fbot.core.commands import CancelAlgo, CancelOrder, PlaceAlgo, PlaceOrder
from fbot.execution.queue import ENTRY, EXIT, PROTECT, ExecutionQueue, classify

ENTRY_CMD = PlaceOrder("XUSDT", "BUY", "MARKET", D("1"), None, False, "p0Labc", None)
EXIT_CMD = PlaceOrder("XUSDT", "SELL", "MARKET", D("1"), None, True, "p0Labc-X-v1", None)
ALGO_CMD = PlaceAlgo("XUSDT", "SELL", "STOP_MARKET", D("99"), True, "MARK_PRICE", True, "p0Labc-SL-v1")


def test_classify_separates_entry_from_protection_and_exit():
    assert classify(ENTRY_CMD) == ENTRY
    assert classify(EXIT_CMD) == EXIT
    assert classify(ALGO_CMD) == PROTECT
    assert classify(CancelAlgo("XUSDT", "p0Labc-SL-v1")) == PROTECT
    assert classify(CancelOrder("XUSDT", "p0Labc")) == PROTECT


def test_entries_are_refused_before_the_reserve_is_touched():
    q = ExecutionQueue(maxsize=5, reserve_slots=2)
    for _ in range(3):
        assert q.put(ENTRY_CMD, 0)[0]
    ok, klass = q.put(ENTRY_CMD, 0)          # 2 slot kaldı = rezerv
    assert not ok and klass == ENTRY and q.stats["rejected"][ENTRY] == 1
    assert q.put(ALGO_CMD, 0)[0] and q.put(EXIT_CMD, 0)[0], "rezerv koruma/çıkış için ayrıldı"


def test_full_queue_refuses_everything_but_counts_it():
    q = ExecutionQueue(maxsize=2, reserve_slots=1)
    assert q.put(ALGO_CMD, 0)[0] and q.put(EXIT_CMD, 0)[0]
    assert not q.put(EXIT_CMD, 0)[0]
    assert q.stats["rejected"][EXIT] == 1


def test_reserve_must_be_smaller_than_the_queue():
    with pytest.raises(ValueError):
        ExecutionQueue(maxsize=4, reserve_slots=4)


def test_sending_does_not_block_the_event_loop():
    """G testi: 200 ms'lik HTTP çağrısı sırasında döngü başka iş yapabilmeli."""
    def slow_send(cmd, now_ns):
        time.sleep(0.2)
        return {"kind": "order_ack", "client_id": cmd.client_id}

    async def main():
        q = ExecutionQueue(maxsize=10, reserve_slots=2)
        results = []
        q.start(slow_send, lambda c, k, out, err, t0, rtt: results.append((k, out, err)))
        q.put(ENTRY_CMD, 0)
        ticks = 0
        t0 = time.perf_counter()
        while not results:
            await asyncio.sleep(0.005)
            ticks += 1
        assert ticks > 10, f"döngü gönderim boyunca {ticks} kez dönebildi"
        assert time.perf_counter() - t0 >= 0.2
        assert results[0][0] == ENTRY and results[0][1]["kind"] == "order_ack"
        await q.aclose()
    asyncio.run(main())


def test_fifo_order_is_preserved_across_classes():
    def send(cmd, now_ns):
        return {"cid": getattr(cmd, "client_id", None) or cmd.client_algo_id}

    async def main():
        q = ExecutionQueue(maxsize=10, reserve_slots=2)
        seen = []
        q.start(send, lambda c, k, out, err, t0, rtt: seen.append(out["cid"]))
        for cmd in (ENTRY_CMD, ALGO_CMD, EXIT_CMD):
            q.put(cmd, 0)
        await q.drain()
        await q.aclose()
        assert seen == ["p0Labc", "p0Labc-SL-v1", "p0Labc-X-v1"]
    asyncio.run(main())


def test_a_failing_send_is_reported_not_swallowed():
    def boom(cmd, now_ns):
        raise RuntimeError("bağlantı koptu")

    async def main():
        q = ExecutionQueue(maxsize=4, reserve_slots=1)
        seen = []
        q.start(boom, lambda c, k, out, err, t0, rtt: seen.append(err))
        q.put(EXIT_CMD, 0)
        await q.drain()
        await q.aclose()
        assert isinstance(seen[0], RuntimeError) and q.stats["failed"] == 1
    asyncio.run(main())


def test_round_trip_time_is_measured():
    def send(cmd, now_ns):
        time.sleep(0.05)
        return {}

    async def main():
        q = ExecutionQueue(maxsize=4, reserve_slots=1)
        rtts = []
        q.start(send, lambda c, k, out, err, t0, rtt: rtts.append(rtt))
        q.put(EXIT_CMD, 0)
        await q.drain()
        await q.aclose()
        assert rtts[0] >= 50_000_000
    asyncio.run(main())
