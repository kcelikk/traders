"""Emir gönderim kuyruğu (Gate 2.1). I/O kenarı; olay döngüsünü bloke etmez.

Bugün `TestnetTrader._send` `adapter.submit`'i **doğrudan** çağırıyor: HTTP isteği olay işleme
yolunun içinde, senkron. Ölçülen loop lag dikeni bu yüzden 3,2 s'ye çıkıyor (`docs/gate1-olcum.md` §6).

Burada komut sınırlı bir kuyruğa alınır; tek bir işçi görevi kuyruğu FIFO boşaltır ve HTTP çağrısını
`asyncio.to_thread` ile yapar. Sonuç, tek sıralama noktasından (`Recorder.emit`) `exec` olayı olarak
akışa yazılır; replay'de bu olaylar kayıttan okunur, yeniden çalıştırılmaz (Rule Zero korunur).

**Sınıf bazlı rezerv:** kuyruk dolmaya yaklaşınca önce giriş emirleri reddedilir. Koruma ve çıkış
emirleri için ayrılmış slot her zaman durur — pozisyonu kapatamamak, açamamaktan pahalıdır.
Bu, `RateLimiter.reserve_orders` kuralının kuyruk karşılığıdır.

FIFO bozulmaz: rezerv bir **kabul** kuralıdır, sıra değiştirme değil. Aynı pozisyonun emirleri
gönderim sırasını korur.
"""
from __future__ import annotations

import asyncio

ENTRY = "entry"        # yeni pozisyon açan emir — sıkışıklıkta ilk feda edilen
PROTECT = "protect"    # SL/TP algo emri ve iptali
EXIT = "exit"          # reduceOnly kapatma emri
CLASSES = (ENTRY, PROTECT, EXIT)


def classify(cmd) -> str:
    """Komut sınıfı: tip ve `reduce_only` bayrağından. Bilinmeyen tip giriş sayılmaz (fail-closed:
    korumayı düşürmemek için PROTECT'e değil, en kısıtlı sınıfa konur)."""
    name = type(cmd).__name__
    if name in ("PlaceAlgo", "CancelAlgo"):
        return PROTECT
    if name == "PlaceOrder":
        return EXIT if getattr(cmd, "reduce_only", False) else ENTRY
    if name == "CancelOrder":
        return PROTECT
    return ENTRY


class ExecutionQueue:
    def __init__(self, maxsize: int = 256, reserve_slots: int = 8):
        if reserve_slots >= maxsize:
            raise ValueError("reserve_slots < queue_max olmalı")
        self.maxsize = maxsize
        self.reserve_slots = reserve_slots
        self.q: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self.sent = 0
        self.rejected = {c: 0 for c in CLASSES}
        self.failed = 0
        self.depth_max = 0
        self._depth: list[int] = []
        self._task: asyncio.Task | None = None

    # ---- kabul
    def put(self, cmd, now_ns: int) -> tuple[bool, str]:
        """(kabul edildi mi, sınıf). Reddedilen komut **sayılır**; sessizce düşmez."""
        klass = classify(cmd)
        free = self.maxsize - self.q.qsize()
        if free <= 0 or (klass == ENTRY and free <= self.reserve_slots):
            self.rejected[klass] += 1
            return False, klass
        self.q.put_nowait((cmd, klass, now_ns))
        d = self.q.qsize()
        self.depth_max = max(self.depth_max, d)
        if len(self._depth) < 10_000:
            self._depth.append(d)
        return True, klass

    # ---- işçi
    def start(self, send, on_result) -> asyncio.Task:
        """`send(cmd, now_ns) -> dict` bloklayan çağrıdır, thread'e taşınır.
        `on_result(cmd, klass, result | None, error | None, sent_ns, rtt_ns)` döngü thread'inde çalışır."""
        if self._task is None:
            self._task = asyncio.create_task(self.run(send, on_result))
        return self._task

    async def run(self, send, on_result) -> None:
        loop = asyncio.get_running_loop()
        while True:
            cmd, klass, queued_ns = await self.q.get()
            t0 = loop.time()
            try:
                out = await asyncio.to_thread(send, cmd, queued_ns)
                err = None
            except Exception as e:  # noqa: BLE001 — gönderim hatası koşuyu durdurmaz, olaya yazılır
                out, err = None, e
                self.failed += 1
            else:
                self.sent += 1
            rtt_ns = int((loop.time() - t0) * 1e9)
            try:
                on_result(cmd, klass, out, err, queued_ns, rtt_ns)
            finally:
                self.q.task_done()

    async def drain(self) -> None:
        await self.q.join()

    async def aclose(self) -> None:
        await self.drain()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    @property
    def stats(self) -> dict:
        d = sorted(self._depth)
        p99 = d[min(len(d) - 1, int(0.99 * (len(d) - 1) + 0.5))] if d else 0
        return {"queued": self.q.qsize(), "sent": self.sent, "failed": self.failed,
                "rejected": dict(self.rejected), "depth_p99": p99, "depth_max": self.depth_max}
