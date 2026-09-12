"""User data stream bağlantısı (Gate 3b): listenKey yaşam döngüsü, keepalive, expired → yeniden bağlan.

Keepalive bu yöneticinin parçasıdır (ADR 0003); ayrı bir döngü yazılmaz. Sahte WS sunucusu ve
sahte REST ile test edilir; gerçek borsaya bağlanılmaz.
"""
import asyncio
import json

import pytest

from fbot.gateway.userdata import UserDataConnection, mask
from tests.fake import FakeWSServer, Session, listen_key_expired, order_trade_update


def conn(server_url, keys, keepalive=None, **kw):
    frames = []
    ctrl = []
    keys = list(keys)

    def get_key():
        return keys.pop(0) if keys else "kTAIL"
    c = UserDataConnection(base_url=server_url.rstrip("/").replace("/ws", ""), get_key=get_key,
                           keepalive=keepalive or (lambda: None),
                           on_frame=lambda raw, r, m: frames.append(raw),
                           on_ctrl=lambda kind, info: ctrl.append((kind, info)), **kw)
    return c, frames, ctrl


def test_key_is_masked_everywhere_it_is_reported():
    assert mask("abcdef1234567890XYZW") == "…XYZW"
    assert mask("abc") == ""


def test_connects_with_a_fresh_key_and_delivers_frames():
    async def main():
        payload = json.dumps(order_trade_update(client_id="t0Labc", symbol="BTCUSDT"))
        async with FakeWSServer([Session(frames=[payload], hold_s=0.4)]) as srv:
            c, frames, ctrl = conn(srv.url, ["key-AAAA1234"], keepalive_s=10, jitter_s=0)
            task = asyncio.ensure_future(c.run())
            for _ in range(60):
                await asyncio.sleep(0.02)
                if frames:
                    break
            c.stop()
            await asyncio.gather(task, return_exceptions=True)
        assert frames and json.loads(frames[0])["e"] == "ORDER_TRADE_UPDATE"
        assert c.stats["keys"] == 1 and c.stats["frames"] == 1
        kinds = [k for k, _ in ctrl]
        assert "listen_key" in kinds and "connect" in kinds
        # Anahtar hiçbir olayda açık yazılmaz
        assert all("key-AAAA1234" not in json.dumps(info) for _, info in ctrl)
    asyncio.run(main())


def test_expired_key_triggers_a_reconnect_with_a_new_key():
    async def main():
        expired = json.dumps(listen_key_expired())
        async with FakeWSServer([Session(frames=[expired], hold_s=2.0), Session(frames=[], hold_s=0.5)]) as srv:
            c, frames, ctrl = conn(srv.url, ["key-FIRST123", "key-SECOND12"], keepalive_s=30, jitter_s=0)
            task = asyncio.ensure_future(c.run())
            for _ in range(100):
                await asyncio.sleep(0.02)
                if c.stats["keys"] >= 2:
                    break
            c.stop()
            await asyncio.gather(task, return_exceptions=True)
        assert c.stats["expired"] == 1, "listenKeyExpired görülmedi"
        assert c.stats["keys"] >= 2, "yeni key alınmadı"
        assert "listen_key_expired" in [k for k, _ in ctrl]
    asyncio.run(main())


def test_keepalive_runs_on_schedule_and_reports():
    async def main():
        calls = []
        async with FakeWSServer([Session(frames=[], hold_s=1.5)]) as srv:
            c, frames, ctrl = conn(srv.url, ["key-AAAA1234"], keepalive=lambda: calls.append(1),
                                   keepalive_s=1.0, jitter_s=0)
            task = asyncio.ensure_future(c.run())
            for _ in range(100):
                await asyncio.sleep(0.02)
                if calls:
                    break
            c.stop()
            await asyncio.gather(task, return_exceptions=True)
        assert calls and c.stats["keepalives"] >= 1
        assert "listen_key_keepalive" in [k for k, _ in ctrl]
    asyncio.run(main())


def test_keepalive_failure_is_not_swallowed():
    """Sessiz keepalive hatası: key 60 dk sonra ölür ve akış fark edilmeden susar."""
    async def main():
        def boom():
            raise OSError("keepalive reddedildi")
        async with FakeWSServer([Session(frames=[], hold_s=1.5)]) as srv:
            c, frames, ctrl = conn(srv.url, ["key-AAAA1234", "key-BBBB5678"], keepalive=boom,
                                   keepalive_s=1.0, jitter_s=0)
            task = asyncio.ensure_future(c.run())
            for _ in range(100):
                await asyncio.sleep(0.02)
                if c.stats["keepalive_errors"]:
                    break
            c.stop()
            await asyncio.gather(task, return_exceptions=True)
        kinds = [k for k, _ in ctrl]
        assert c.stats["keepalive_errors"] >= 1
        assert "listen_key_keepalive_error" in kinds
        assert "force_reconnect" in kinds, "hata sonrası yeniden bağlanma istenmedi"
    asyncio.run(main())


def test_stream_age_is_tracked_separately_from_market_staleness():
    async def main():
        async with FakeWSServer([Session(frames=[json.dumps(order_trade_update(client_id="t0Labc"))], hold_s=0.4)]) as srv:
            c, frames, _ = conn(srv.url, ["key-AAAA1234"], keepalive_s=10, jitter_s=0)
            assert c.age_s() is None, "hiç çerçeve gelmediyse yaş bilinmiyor, sıfır değil"
            task = asyncio.ensure_future(c.run())
            for _ in range(60):
                await asyncio.sleep(0.02)
                if frames:
                    break
            age = c.age_s()
            c.stop()
            await asyncio.gather(task, return_exceptions=True)
        assert age is not None and age < 5
    asyncio.run(main())


def test_jitter_is_seeded_so_timing_is_reproducible():
    a, _, _ = conn("ws://x", ["k"], seed=7, keepalive_s=100, jitter_s=10)
    b, _, _ = conn("ws://x", ["k"], seed=7, keepalive_s=100, jitter_s=10)
    assert [a._rng.uniform(-10, 10) for _ in range(3)] == [b._rng.uniform(-10, 10) for _ in range(3)]


def test_private_category_does_not_break_the_market_staleness_watcher(tmp_path):
    """Private bağlantı koşu sırasında eklenir. İzleyici sözlüğü döngü içinde büyürse çöker;
    ayrıca private'ın market eşiğiyle zorla yeniden bağlanması yanlıştır (sessizlik normaldir)."""
    from fbot.config import load_recorder_config
    from fbot.recorder.main import Recorder

    cfg, h = load_recorder_config("config/testnet.toml")
    cfg = type(cfg)(**{**cfg.__dict__, "out_dir": str(tmp_path)})
    r = Recorder(cfg, h, "t", None)

    class Conn:
        last_frame_mono_ns = 1
        async def force_reconnect(self, reason):
            raise AssertionError("private akış market eşiğiyle yeniden bağlanmamalı")

    r.conns["private"] = Conn()
    assert "private" not in cfg.staleness_s, "private'ın market eşiği olmamalı"

    async def main():
        task = asyncio.ensure_future(r.staleness_task())
        await asyncio.sleep(1.2)
        r.stop_ev.set()
        await asyncio.gather(task, return_exceptions=True)
    asyncio.run(main())


def test_core_ignores_private_frames_in_shadow_mode():
    """Gate 3b çıkış koşulu: private kategori çekirdeğe girse bile komut üretmez ve hash'i değiştirmez.
    Kayıt replay'i user data çerçevelerini de içerecek; davranış kasıtlı olmalı, kaza olmamalı."""
    from fbot.core.commands import canonical
    from fbot.core.engine import CoreConfig, CoreState, Engine
    from fbot.events import RawEvent

    eng = Engine(CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000}))
    frames = [json.dumps(order_trade_update(client_id="t0Labc", status="FILLED", exec_type="TRADE",
                                            last_price="100", last_qty="1", cum_qty="1")).encode(),
              json.dumps(listen_key_expired()).encode()]

    st, out = CoreState(), []
    for i, raw in enumerate(frames, 1):
        st, cmds = eng.step(st, RawEvent(i, i, i, "private", "user", raw), i)
        out += cmds
    assert out == [], "shadow modda private çerçeve komut üretmemeli"
    assert st.private_events == 2 and st.parse_errors == 0

    # Aynı akış private çerçeveler olmadan: komut dizisi aynı (hash-nötrlük)
    st2, out2 = CoreState(), []
    st2, cmds = eng.step(st2, RawEvent(1, 1, 1, "ctrl", "tick", b'{"n":1}'), 1)
    out2 += cmds
    st3, cmds = eng.step(CoreState(), RawEvent(1, 1, 1, "ctrl", "tick", b'{"n":1}'), 1)
    assert [canonical(c) for c in out2] == [canonical(c) for c in cmds]
