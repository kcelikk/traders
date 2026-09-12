"""Kategori başına WS bağlantı yöneticisi. I/O kenarı.

Bir bağlantı = bir kategori (/public, /market, /private). Çerçeveler geldiği sırayla,
aynı döngü içinde senkron olarak `on_frame(raw, recv_ns, mono_ns)` ile teslim edilir;
sıralama noktası çağıranın Sequencer'ıdır. Kopmada üstel geri çekilmeyle yeniden bağlanır.
"""
from __future__ import annotations

import asyncio
import time
from typing import Callable

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

OnFrame = Callable[[bytes, int, int], None]
OnCtrl = Callable[[str, dict], None]


def _safe_url(url: str) -> str:
    """listenKey URL yolunda taşınır ve gizlidir: kayda, log'a, ctrl olayına maskeli girer."""
    head, sep, tail = url.rpartition("/")
    if sep and len(tail) > 8 and "?" not in url:
        return f"{head}/…{tail[-4:]}"
    return url


class CategoryConnection:
    """`url_factory` verilirse **her bağlanmada** çağrılır (private akış: listenKey her seferinde
    yenilenebilir). Böylece backoff, `force_reconnect` ve ctrl olayları yeniden kullanılır; private
    için ayrı bir bağlantı sınıfı yazılmaz."""

    def __init__(self, name: str, url: str, on_frame: OnFrame, on_ctrl: OnCtrl,
                 backoff_initial_s: float = 1.0, backoff_max_s: float = 30.0, max_queue: int = 4096,
                 url_factory=None):
        self.name = name
        self.url = url
        self.url_factory = url_factory
        self.on_frame = on_frame
        self.on_ctrl = on_ctrl
        self.backoff_initial_s = backoff_initial_s
        self.backoff_max_s = backoff_max_s
        self.max_queue = max_queue
        self.last_frame_mono_ns = 0
        self.connects = 0
        self.frames = 0
        self._stop = asyncio.Event()
        self._ws = None

    def stop(self):
        """Döngü içinden çağrılır: durdurma bayrağı + açık soketi kapat (recv beklemesini keser)."""
        self._stop.set()
        if self._ws is not None:
            asyncio.get_running_loop().create_task(self._ws.close())

    async def force_reconnect(self, reason: str):
        """Bayatlık izleyicisi çağırır: mevcut bağlantıyı kapat, döngü yeniden bağlanır."""
        self.on_ctrl("force_reconnect", {"cat": self.name, "reason": reason})
        if self._ws is not None:
            await self._ws.close()

    async def run(self):
        backoff = self.backoff_initial_s
        while not self._stop.is_set():
            t0 = time.monotonic_ns()
            try:
                if self.url_factory is not None:
                    self.url = await self.url_factory()
                async with connect(self.url, max_queue=self.max_queue, ping_interval=20, ping_timeout=20) as ws:
                    self._ws = ws
                    self.connects += 1
                    backoff = self.backoff_initial_s
                    self.on_ctrl("connect", {"cat": self.name, "url": _safe_url(self.url),
                                             "connect_ms": (time.monotonic_ns() - t0) // 10**6, "n": self.connects})
                    async for raw in ws:
                        recv_ns = time.time_ns()
                        mono_ns = time.monotonic_ns()
                        if isinstance(raw, str):
                            raw = raw.encode()
                        self.last_frame_mono_ns = mono_ns
                        self.frames += 1
                        self.on_frame(raw, recv_ns, mono_ns)
                        if self._stop.is_set():
                            break
                    self.on_ctrl("disconnect", {"cat": self.name, "reason": "closed", "code": getattr(ws, "close_code", None)})
            except ConnectionClosed as e:
                self.on_ctrl("disconnect", {"cat": self.name, "reason": "closed", "code": e.code if hasattr(e, "code") else None})
            except Exception as e:  # noqa: BLE001 — kenar: her hata kayda geçer, döngü sürer
                self.on_ctrl("disconnect", {"cat": self.name, "reason": "error", "err": repr(e)})
            finally:
                self._ws = None
            if self._stop.is_set():
                break
            self.on_ctrl("reconnect_wait", {"cat": self.name, "backoff_s": backoff})
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, self.backoff_max_s)
