"""Sahte WS sunucusu: N mesaj gönderir, bağlantıyı kapatır; gateway yeniden bağlanmalı, seq kesintisiz olmalı."""
import asyncio
import json

from websockets.asyncio.server import serve

from fbot.gateway.ws_category import CategoryConnection
from fbot.sequencer import Sequencer


def test_reconnect_after_server_close():
    asyncio.run(_run())


async def _run():
    sessions = 0

    async def handler(ws):
        nonlocal sessions
        sessions += 1
        base = (sessions - 1) * 3
        for i in range(3):
            await ws.send(json.dumps({"stream": "btcusdt@aggTrade", "data": {"e": "aggTrade", "a": base + i}}))
        if sessions == 1:
            await ws.close()  # ilk oturumu sunucu kapatır
        else:
            await asyncio.sleep(5)

    got = []
    sq = Sequencer()

    def on_frame(raw, recv_ns, mono_ns):
        got.append(sq.next(recv_ns, mono_ns, "public", "btcusdt@aggTrade", raw))

    ctrl = []
    async with serve(handler, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        conn = CategoryConnection(
            name="public", url=f"ws://127.0.0.1:{port}/", on_frame=on_frame,
            on_ctrl=lambda kind, info: ctrl.append(kind), backoff_initial_s=0.05, backoff_max_s=0.1,
        )
        task = asyncio.create_task(conn.run())
        for _ in range(100):
            await asyncio.sleep(0.05)
            if len(got) >= 6:
                break
        conn.stop()
        await asyncio.wait_for(task, 3)
    assert sessions >= 2
    assert [e.seq for e in got[:6]] == [1, 2, 3, 4, 5, 6]
    assert ctrl.count("connect") >= 2 and "disconnect" in ctrl
    assert conn.last_frame_mono_ns > 0
