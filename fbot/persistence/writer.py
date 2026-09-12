"""Kalıcılık kuyruğu: SQLite yazımını olay işleme yolundan çıkarır. I/O kenarı.

Neden: `PaperTrader._record_*` bugün her olayda senkron `INSERT` yapıyor; disk yavaşladığında
market olayı işleme de yavaşlıyor. Burada yazım sınırlı bir kuyruğa alınır, ayrı bir görev
toplu hâlde ve `asyncio.to_thread` ile uygular; böylece SQLite hiçbir zaman döngüyü tutmaz.

Kuyruk dolarsa **düşürülür ve sayılır** — sessiz kayıp yok. Düşen satır görünüm/rapor verisidir,
karar verisi değil: çekirdek durumu bellekte, ham akış recorder dosyasındadır.
"""
from __future__ import annotations

import asyncio

KINDS = ("decision", "order", "fill", "position")


def _p(samples: list[int], q: float) -> int:
    if not samples:
        return 0
    s = sorted(samples)
    return s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))]


class AsyncStore:
    """`PaperStore` ile aynı yazım arayüzü; çağrı anında yalnızca kuyruğa koyar.

    Okuma ve meta yazımları (config, heartbeat) doğrudan geçer: bunlar hot path'te değildir ve
    `PaperStore` bağlantısı kilitle korunur.
    """

    def __init__(self, store, maxsize: int = 20_000, batch: int = 500, max_samples: int = 10_000):
        self.store = store
        self.batch = batch
        self.max_samples = max_samples
        self.q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self.written = 0
        self.dropped = 0
        self.errors = 0
        self.last_error: str | None = None
        self.depth_max = 0
        self._depth: list[int] = []
        self._task: asyncio.Task | None = None

    # ---- kuyruğa alınan yazımlar (çağıran bloke olmaz)
    def record_decision(self, d: dict) -> None:
        self._put("decision", d)

    def record_order(self, o: dict) -> None:
        self._put("order", o)

    def record_fill(self, f: dict) -> None:
        self._put("fill", f)

    def record_position(self, p: dict) -> None:
        self._put("position", p)

    def _put(self, kind: str, payload: dict) -> None:
        try:
            self.q.put_nowait((kind, payload))
        except asyncio.QueueFull:
            self.dropped += 1

    # ---- görev
    def start(self) -> asyncio.Task:
        if self._task is None:
            self._task = asyncio.create_task(self.run())
        return self._task

    async def run(self) -> None:
        while True:
            item = await self.q.get()
            batch = [item]
            while len(batch) < self.batch:
                try:
                    batch.append(self.q.get_nowait())
                except asyncio.QueueEmpty:
                    break
            depth = self.q.qsize() + len(batch)
            self.depth_max = max(self.depth_max, depth)
            if len(self._depth) < self.max_samples:
                self._depth.append(depth)
            try:
                await asyncio.to_thread(self._apply, batch)
                self.written += len(batch)
            except Exception as e:  # noqa: BLE001 — kalıcılık hatası koşuyu durdurmaz, sayılır
                self.errors += 1
                self.last_error = repr(e)[:200]
            finally:
                for _ in batch:
                    self.q.task_done()

    def _apply(self, batch: list[tuple[str, dict]]) -> None:
        """Ayrı thread: `PaperStore` bağlantısı kilitlidir, döngü thread'i aynı anda okuyabilir."""
        s = self.store
        fn = {"decision": s.record_decision, "order": s.record_order, "fill": s.record_fill, "position": s.record_position}
        for kind, payload in batch:
            fn[kind](payload)
        s.flush()

    async def drain(self) -> None:
        """Kuyruktaki her şey diske yazılana kadar bekler (kapanışta kayıp olmasın)."""
        await self.q.join()

    async def aclose(self) -> None:
        await self.drain()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None
        await asyncio.to_thread(self.store.flush)

    @property
    def stats(self) -> dict:
        return {"queued": self.q.qsize(), "written": self.written, "dropped": self.dropped,
                "depth_p99": _p(self._depth, 0.99), "depth_max": self.depth_max,
                "errors": self.errors, "last_error": self.last_error}

    # ---- doğrudan geçenler (hot path'te değil)
    def set_config(self, *a, **k):
        return self.store.set_config(*a, **k)

    def get_config(self):
        return self.store.get_config()

    def heartbeat(self, *a, **k):
        return self.store.heartbeat(*a, **k)

    def get_heartbeat(self):
        return self.store.get_heartbeat()

    def summary(self) -> dict:
        return self.store.summary()

    def runs(self) -> list[dict]:
        return self.store.runs()

    def recent_positions(self, n: int = 20):
        return self.store.recent_positions(n)

    def recent_decisions(self, n: int = 20):
        return self.store.recent_decisions(n)

    def flush(self) -> None:
        self.store.flush()

    def close(self) -> None:
        self.store.close()

    @property
    def run_id(self) -> str:
        return self.store.run_id

    @property
    def env(self) -> str:
        return self.store.env
