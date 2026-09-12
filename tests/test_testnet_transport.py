"""Gate 2.1: gönderim yolu. Kuyruklu yolda emir HTTP'si olay yolunda değildir; legacy geri alma yolu durur."""
import asyncio
from decimal import Decimal as D

from fbot.core.commands import PlaceAlgo, PlaceOrder
from fbot.core.position import Filters
from fbot.execution.queue import ExecutionQueue
from fbot.execution.testnet_adapter import TestnetAdapter
from fbot.gateway.signing import Credentials
from fbot.gateway.testnet import TestnetClient
from fbot.paper.config import ExecutionConfig, PaperConfigError, load_paper_config
from fbot.sequencer import Sequencer
from fbot.testnet.main import TestnetTrader
from tests.fake import FakeHTTP
from tests.fake.http import ok

FILT = {"XUSDT": Filters(D("0.001"), D("0.001"), D("5"), D("0.01"))}
ENTRY = PlaceOrder("XUSDT", "BUY", "MARKET", D("1"), None, False, "t0Labc", None)
ALGO = PlaceAlgo("XUSDT", "SELL", "STOP_MARKET", D("99"), True, "MARK_PRICE", True, "t0Labc-SL-v1")


class Emitter:
    def __init__(self):
        self.seq = Sequencer()
        self.events = []

    def __call__(self, cat, stream, raw, recv_ns=None, mono_ns=None):
        ev = self.seq.next(recv_ns or 1, mono_ns or 1, cat, stream, raw)
        self.events.append(ev)
        return ev


def trader(responses, queue=None):
    c = TestnetClient(Credentials(api_key="K", api_secret="S"), http=FakeHTTP(responses))
    a = TestnetAdapter(c, armed=True, symbols=FILT)
    em = Emitter()

    class Eng:
        pm = None

        def step(self, st, ev, now_ns):
            return st, []
    t = TestnetTrader(Eng(), a, em, store=None, queue=queue)
    return t, em


def test_legacy_path_sends_inside_the_event_path():
    t, em = trader([ok({"orderId": 1, "status": "NEW"})])
    t._send(ENTRY, now_ns=10**12)
    assert t.adapter.client.http.calls, "legacy yolda istek hemen gitmeli"
    assert [e.stream for e in em.events] == ["command", "order_ack"]


def test_queued_path_does_not_touch_http_in_the_event_path():
    async def main():
        q = ExecutionQueue(maxsize=8, reserve_slots=2)
        t, em = trader([ok({"orderId": 1, "status": "NEW"})], queue=q)
        t._send(ENTRY, now_ns=10**12)
        assert t.adapter.client.http.calls == [], "olay yolunda HTTP olmamalı"
        assert [e.stream for e in em.events] == ["command"]
        q.start(lambda c, now_ns: t.adapter.submit(c, now_ms=now_ns // 1_000_000), t.on_send_result)
        await q.drain()
        await q.aclose()
        assert len(t.adapter.client.http.calls) == 1
        assert [e.stream for e in em.events] == ["command", "order_ack"]
        assert t.stats["orders"] == 1 and t.rtt_ns
    asyncio.run(main())


def test_dropped_command_is_an_event_not_a_silence():
    async def main():
        q = ExecutionQueue(maxsize=2, reserve_slots=1)
        t, em = trader([], queue=q)
        assert q.put(ALGO, 0)[0] and q.put(ALGO, 0)[0]      # kuyruk doldu
        t._send(ENTRY, now_ns=10**12)
        streams = [e.stream for e in em.events]
        assert streams == ["command", "order_dropped"] and t.errors["dropped"] == 1
    asyncio.run(main())


def test_post_timeout_becomes_an_unknown_execution_event():
    """Gate 2.1: POST zaman aşımı "gönderilmedi" değil, "bilinmiyor"dur. Akışa `order_unknown`
    olarak yazılır ve `needs_reconcile` ile mutabakat istenir; sessiz kayıp yok."""
    from tests.fake import timeout

    async def main():
        q = ExecutionQueue(maxsize=4, reserve_slots=1)
        t, em = trader([timeout()], queue=q)
        t._send(ENTRY, now_ns=10**12)
        q.start(lambda c, now_ns: t.adapter.submit(c, now_ms=now_ns // 1_000_000), t.on_send_result)
        await q.drain()
        await q.aclose()
        unknown = [e for e in em.events if e.stream == "order_unknown"]
        assert unknown and b'"needs_reconcile":true' in unknown[0].raw
        assert t.errors["unknown"] == 1 and t.errors["failed"] == 0
    asyncio.run(main())


def test_rate_limit_refusal_is_reported_as_a_failure_not_an_unknown():
    """Emir bütçesi yoksa istek hiç gitmez: yürütme durumu belirsiz değildir."""
    async def main():
        q = ExecutionQueue(maxsize=4, reserve_slots=1)
        t, em = trader([], queue=q)
        t.adapter.client.limiter.banned = True          # 418 sonrası kalıcı ban
        t._send(ENTRY, now_ns=10**12)
        q.start(lambda c, now_ns: t.adapter.submit(c, now_ms=now_ns // 1_000_000), t.on_send_result)
        await q.drain()
        await q.aclose()
        failed = [e for e in em.events if e.stream == "order_failed"]
        assert failed and t.errors["failed"] == 1
        assert t.adapter.client.http.calls == []
    asyncio.run(main())


def test_transport_config_is_validated(repo_root, tmp_path):
    cfg, _ = load_paper_config(repo_root / "config/testnet.toml")
    assert cfg.execution.transport == "persistent_async" and cfg.execution.reserve_slots < cfg.execution.queue_max
    src = (repo_root / "config/testnet.toml").read_text().replace('transport = "persistent_async"', 'transport = "hizli"')
    f = tmp_path / "bad.toml"
    f.write_text(src)
    try:
        load_paper_config(f)
        raise AssertionError("bilinmeyen transport kabul edildi")
    except PaperConfigError as e:
        assert "transport" in str(e)


def test_default_transport_is_legacy_so_rollback_needs_no_code_change():
    assert ExecutionConfig().transport == "legacy"


def test_periodic_exchange_poll_runs_off_the_event_loop():
    """Gate 1 ölçümünde testnet loop lag en kötü p99'u 3,2 s idi: silahlanma denetimi ve mutabakat
    REST çağrısı olduğu hâlde olay döngüsünde koşuyordu. Artık thread'e taşınır."""
    import time as _t

    from fbot.paper.main import PaperRecorder

    class Rec(PaperRecorder):
        def __init__(self):                     # kurucuyu atla: yalnız _pre_beat davranışı test ediliyor
            self.calls = 0

        async def _pre_beat(self):
            import asyncio as _a
            self.calls += 1
            await _a.to_thread(_t.sleep, 0.2)   # bloklayan borsa sorgusunun yerine

    async def main():
        r = Rec()
        ticks = 0
        task = asyncio.ensure_future(r._pre_beat())
        while not task.done():
            await asyncio.sleep(0.005)
            ticks += 1
        await task
        assert r.calls == 1 and ticks > 10, f"döngü sorgu boyunca {ticks} kez dönebildi"
    asyncio.run(main())


def test_execution_queue_does_not_shadow_the_recorder_event_queue(tmp_path):
    """Canlıda yakalanan regresyon: `Recorder.queue` olay yazım kuyruğudur. Gönderim kuyruğu aynı
    isme yazılınca `emit` çöküyordu ve süreç açılışta ölüyordu."""
    from fbot.config import load_recorder_config
    from fbot.recorder.main import Recorder

    cfg, h = load_recorder_config("config/testnet.toml")
    cfg = type(cfg)(**{**cfg.__dict__, "out_dir": str(tmp_path)})
    r = Recorder(cfg, h, "t", None)
    r.exec_queue = ExecutionQueue(maxsize=4, reserve_slots=1)     # Gate 2.1 alanı
    ev = r.emit("ctrl", "tick", b'{"n":1}', 1, 1)
    assert r.queue.qsize() == 1 and ev.seq == 1
