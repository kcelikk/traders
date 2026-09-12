"""Kalıcılık kuyruğu (Gate 1): yazım hot path'ten çıkar, kayıp sessiz olmaz.

F testi: yavaş SQLite yazıcısı market olayı işlemeyi bloklamamalı.
"""
import asyncio
import time

import pytest

from fbot.paper.store import PaperStore
from fbot.persistence.writer import AsyncStore


class SlowStore:
    """Her yazımda 20 ms uyuyan sahte store (yavaş disk)."""

    def __init__(self, delay=0.02):
        self.delay = delay
        self.rows = []
        self.flushes = 0

    def _w(self, kind, d):
        time.sleep(self.delay)
        self.rows.append((kind, d))

    def record_decision(self, d): self._w("decision", d)
    def record_order(self, d): self._w("order", d)
    def record_fill(self, d): self._w("fill", d)
    def record_position(self, d): self._w("position", d)
    def flush(self): self.flushes += 1


def test_enqueue_does_not_block_the_event_loop():
    """20 olay × 20 ms = 400 ms'lik yazım; olay işleme bunu beklememeli."""
    async def main():
        st = SlowStore(delay=0.02)
        a = AsyncStore(st, batch=1)
        a.start()
        t0 = time.perf_counter()
        for i in range(20):
            a.record_position({"pos_id": f"p{i}"})
            await asyncio.sleep(0)          # döngüye dönüş: yazıcı çalışsın
        enqueue_s = time.perf_counter() - t0
        assert enqueue_s < 0.05, f"kuyruğa alma bloke oldu: {enqueue_s:.3f} s"
        await a.aclose()
        assert len(st.rows) == 20           # kapanışta hiçbiri kaybolmaz
    asyncio.run(main())


def test_full_queue_drops_and_counts_never_silently():
    async def main():
        a = AsyncStore(SlowStore(delay=0.001), maxsize=5, batch=1)
        for i in range(12):                 # yazıcı görevi başlatılmadı: kuyruk dolar
            a.record_decision({"n": i})
        assert a.q.qsize() == 5 and a.dropped == 7
        assert a.stats["dropped"] == 7
    asyncio.run(main())


def test_order_is_preserved_within_a_kind():
    async def main():
        st = SlowStore(delay=0)
        a = AsyncStore(st, batch=4)
        a.start()
        for i in range(10):
            a.record_fill({"n": i})
        await a.aclose()
        assert [d["n"] for _, d in st.rows] == list(range(10))
    asyncio.run(main())


def test_writer_survives_a_failing_write_and_counts_it():
    class Boom(SlowStore):
        def record_order(self, d):
            raise RuntimeError("disk dolu")

    async def main():
        st = Boom(delay=0)
        a = AsyncStore(st, batch=1)
        a.start()
        a.record_order({"n": 1})
        a.record_fill({"n": 2})
        await a.aclose()
        assert a.errors == 1 and "disk dolu" in a.last_error
        assert [d["n"] for _, d in st.rows] == [2]     # sonraki yazım durmaz
    asyncio.run(main())


def test_queue_depth_is_measured(tmp_path):
    async def main():
        a = AsyncStore(SlowStore(delay=0.005), batch=2)
        a.start()
        for i in range(10):
            a.record_position({"pos_id": f"p{i}"})
        await a.aclose()
        assert a.depth_max >= 2 and a.stats["depth_p99"] >= 1
        assert a.stats["written"] == 10
    asyncio.run(main())


def test_real_store_round_trip_through_the_queue(tmp_path):
    async def main():
        store = PaperStore(tmp_path / "q.db", run_id="r")
        a = AsyncStore(store, batch=3)
        a.start()
        for i in range(5):
            a.record_decision({"t_ms": i, "symbol": "X", "kind": "APPROVE", "reasons": [], "cell": "c", "explain": ""})
        a.record_position({"pos_id": "p1", "symbol": "X", "side": "long", "state": "CLOSED", "qty": "0", "entry_price": "1",
                           "sl": None, "tp": None, "net_pct": "0.3", "exit_reason": "tp", "opened_ns": 1, "closed_ns": 2,
                           "entry_state": "S1"})
        await a.aclose()
        sm = a.summary()
        assert sm["decisions"] == 5 and sm["positions_closed"] == 1
        store.close()
    asyncio.run(main())


def test_hot_path_does_no_sqlite_work_at_all(tmp_path):
    """Ölçüt: olay işleme yolunda SQLite ifadesi sayısı sıfır. Yazım ancak yazıcı görevinde olur."""
    store = PaperStore(tmp_path / "hot.db", run_id="r")
    sql: list[str] = []
    store.con.set_trace_callback(sql.append)

    async def main():
        a = AsyncStore(store, batch=100)
        for i in range(100):
            a.record_decision({"t_ms": i, "symbol": "X", "kind": "APPROVE", "reasons": [], "cell": "c", "explain": ""})
            a.record_position({"pos_id": f"p{i}", "symbol": "X", "side": "long", "state": "MANAGED", "qty": "1",
                               "entry_price": "1", "sl": None, "tp": None, "net_pct": None, "exit_reason": None,
                               "opened_ns": i, "closed_ns": None, "entry_state": "S1"})
        assert sql == [], f"hot path'te {len(sql)} SQL ifadesi çalıştı"
        a.start()
        await a.aclose()
        assert len(sql) > 0 and a.stats["written"] == 200
    asyncio.run(main())
    store.close()
