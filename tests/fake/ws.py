"""Sahte WebSocket sunucusu. Daha önce yalnız `tests/test_gateway_reconnect.py` içinde,
tek senaryoya gömülü hâldeydi.

Senaryo tabanlı: her oturum için ne gönderileceği ve oturumun nasıl biteceği verilir.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from websockets.asyncio.server import serve


@dataclass
class Session:
    """Tek bir bağlantı oturumu: gönderilecek çerçeveler ve sonunda ne olacağı."""
    frames: list[bytes | str] = field(default_factory=list)
    close_after: bool = False          # çerçeveler bitince bağlantıyı kapat (kopma simülasyonu)
    delay_s: float = 0.0               # her çerçeve arası gecikme
    hold_s: float = 5.0                # çerçeveler bitince bağlantıyı bu kadar açık tut
                                       # (sonsuz bekleme kullanılmaz: sunucu kapanışı asılı kalır)


class FakeWSServer:
    """`async with FakeWSServer([Session(...), Session(...)]) as srv:` → `srv.url`

    Her yeni bağlantı sıradaki oturumu alır; oturumlar bitince sonuncusu tekrarlanır.
    """

    def __init__(self, sessions: list[Session]):
        self.sessions = list(sessions) or [Session()]
        self.connections = 0
        self._server = None
        self.url = ""

    async def _handler(self, ws):
        s = self.sessions[min(self.connections, len(self.sessions) - 1)]
        self.connections += 1
        for f in s.frames:
            await ws.send(f)
            if s.delay_s:
                await asyncio.sleep(s.delay_s)
        if s.close_after:
            await ws.close()
            return
        if s.hold_s:
            await asyncio.sleep(s.hold_s)

    async def __aenter__(self):
        self._ctx = serve(self._handler, "127.0.0.1", 0)
        self._server = await self._ctx.__aenter__()
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}/"
        return self

    async def __aexit__(self, *exc):
        await self._ctx.__aexit__(*exc)
