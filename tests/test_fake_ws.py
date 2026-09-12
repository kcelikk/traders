"""Sahte WS sunucusu: kopma, yeniden bağlanma ve gecikmeli çerçeve senaryoları.

`tests/test_gateway_reconnect.py` bu altyapıya taşınabilir; şimdilik ikisi yan yana duruyor
ve aynı davranışı iki farklı yoldan doğruluyor.
"""
import asyncio

from fbot.gateway.ws_category import CategoryConnection
from fbot.sequencer import Sequencer
from tests.fake.ws import FakeWSServer, Session


async def _collect(url, want: int, timeout_s: float = 5.0):
    seq, frames, ctrl = Sequencer(), [], []
    conn = CategoryConnection("market", url, lambda raw, r, m: frames.append(seq.next(r, m, "market", "s", raw)),
                              lambda k, i: ctrl.append((k, i)), backoff_initial_s=0.01, backoff_max_s=0.05)
    task = asyncio.create_task(conn.run())
    t0 = asyncio.get_running_loop().time()
    while len(frames) < want and asyncio.get_running_loop().time() - t0 < timeout_s:
        await asyncio.sleep(0.01)
    conn.stop()
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    return frames, ctrl, conn


def test_disconnect_then_reconnect_keeps_sequence_unbroken():
    async def run():
        async with FakeWSServer([Session(frames=[b'{"a":1}', b'{"a":2}'], close_after=True),
                                 Session(frames=[b'{"a":3}', b'{"a":4}'])]) as srv:
            return await _collect(srv.url, want=4)

    frames, ctrl, conn = asyncio.run(run())
    assert [f.seq for f in frames[:4]] == [1, 2, 3, 4]
    assert conn.connects >= 2
    assert any(k == "disconnect" for k, _ in ctrl)


def test_frames_arrive_in_order_with_delay():
    async def run():
        async with FakeWSServer([Session(frames=[b'{"n":1}', b'{"n":2}', b'{"n":3}'], delay_s=0.01)]) as srv:
            return await _collect(srv.url, want=3)

    frames, _, _ = asyncio.run(run())
    assert [f.raw for f in frames[:3]] == [b'{"n":1}', b'{"n":2}', b'{"n":3}']


def test_server_reports_connection_count():
    async def run():
        async with FakeWSServer([Session(frames=[b'{"x":1}'], close_after=True),
                                 Session(frames=[b'{"x":2}'])]) as srv:
            await _collect(srv.url, want=2)
            return srv.connections

    assert asyncio.run(run()) >= 2
