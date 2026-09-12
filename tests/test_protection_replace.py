"""Koruma yer değiştirmesi (ADR 0023): `-4130` yüzünden ikinci `closePosition` emri konamıyor.

Ölçüm (`docs/measure-4130.json`, testnet'te üç koşu):
  · ikinci `closePosition` STOP → RET -4130
  · `closePosition` STOP yanına TAKE_PROFIT → KABUL
  · iki miktar tabanlı STOP yan yana → KABUL
  · `closePosition` STOP dururken miktar tabanlı STOP → KABUL
  · iptal → yeni sırası: korumasız pencere 817–861 ms
"""
from decimal import Decimal as D

import pytest

from fbot.core.commands import CancelAlgo, PlaceAlgo
from fbot.core.ids import entry_cid
from fbot.core.position import Filters, PosState, Position, PositionConfig, PositionManager

FILT = Filters(D("0.001"), D("0.001"), D("5"), D("0.01"))
CFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                     min_replace_interval_ms=0, taker_fee_pct=D("0.05"), maker_fee_pct=D("0.02"),
                     lock_trigger_pct=D("0.3"), lock_offset_pct=D("0.05"),
                     trail_step_pct=D("0.1"), trail_gap_pct=D("0.3"))
POS = entry_cid("t0", "XUSDT", 60_000, "long")
T = 10**12


def managed():
    pm = PositionManager(CFG)
    p = Position.new(POS, "XUSDT", "long", FILT)
    pm.on_entry_fill(p, D("100"), D("1"), D("99.5"), D("101"), T, entry_state="S1")
    p.state = PosState.MANAGED
    return pm, p


def test_initial_protection_stays_close_position():
    """İlk koruma miktarı otomatik izler: pozisyon küçülse de tamamını kapatır."""
    pm, p = managed()
    cmds = pm.on_entry_fill(p, D("100"), D("1"), D("99.5"), D("101"), T, entry_state="S1")
    algos = [c for c in cmds if isinstance(c, PlaceAlgo)]
    assert len(algos) == 2
    assert all(c.close_position and c.qty is None for c in algos)


def test_replacement_keeps_new_then_cancel_order():
    """Sıra korunur: önce yeni koruma, sonra eskisinin iptali → korumasız pencere yok."""
    pm, p = managed()
    cmds = pm.on_tick(p, T + 10**9, D("100.5"), D("100.4"), D("100.6"), "S1")
    kinds = [type(c).__name__ for c in cmds]
    assert kinds == ["PlaceAlgo", "CancelAlgo"], kinds
    assert isinstance(cmds[1], CancelAlgo)


def test_replacement_is_quantity_based_so_the_exchange_accepts_it():
    """İkinci `closePosition` stop -4130 ile reddediliyor; yer değiştirme miktar tabanlı olmalı."""
    pm, p = managed()
    new = [c for c in pm.on_tick(p, T + 10**9, D("100.5"), D("100.4"), D("100.6"), "S1")
           if isinstance(c, PlaceAlgo)][0]
    assert new.close_position is False and new.qty == D("1")
    assert new.type == "STOP_MARKET" and new.client_algo_id.endswith("-SL-v2")


def test_replacement_quantity_sits_on_the_step_filter():
    pm, p = managed()
    p.qty = D("1.00049")
    new = [c for c in pm.on_tick(p, T + 10**9, D("100.5"), D("100.4"), D("100.6"), "S1")
           if isinstance(c, PlaceAlgo)][0]
    assert new.qty == D("1.000") and new.qty % FILT.step_size == 0


def test_adapter_sends_quantity_and_reduce_only_for_a_quantity_based_algo():
    from tests.fake import FakeHTTP
    from tests.fake.http import ok
    from fbot.execution.testnet_adapter import TestnetAdapter
    from fbot.gateway.signing import Credentials
    from fbot.gateway.testnet import TestnetClient

    c = TestnetClient(Credentials(api_key="K", api_secret="S"), http=FakeHTTP([ok({"algoId": 1, "algoStatus": "NEW"})]))
    a = TestnetAdapter(c, armed=True, symbols={"XUSDT": FILT})
    a.submit(PlaceAlgo("XUSDT", "SELL", "STOP_MARKET", D("99.51"), False, "MARK_PRICE", True, "t0Labc-SL-v2", D("1")), now_ms=0)
    _, _, q, _ = c.http.calls[0]
    assert "closePosition=false" in q and "quantity=1.000" in q and "reduceOnly=true" in q


def test_adapter_refuses_a_quantity_based_algo_without_quantity():
    """Fail-closed: miktarsız `closePosition=false` emri borsada anlamsızdır."""
    from tests.fake import FakeHTTP
    from fbot.execution.testnet_adapter import TestnetAdapter
    from fbot.gateway.signing import Credentials
    from fbot.gateway.testnet import TestnetClient

    c = TestnetClient(Credentials(api_key="K", api_secret="S"), http=FakeHTTP([]))
    a = TestnetAdapter(c, armed=True, symbols={"XUSDT": FILT})
    with pytest.raises(ValueError, match="miktar"):
        a.submit(PlaceAlgo("XUSDT", "SELL", "STOP_MARKET", D("99.51"), False, "MARK_PRICE", True, "x", None), now_ms=0)
    assert c.http.calls == []


def test_close_position_algo_still_sends_no_quantity():
    """`closePosition=true` ile quantity/reduceOnly göndermek -4137/-4138 verir."""
    from tests.fake import FakeHTTP
    from tests.fake.http import ok
    from fbot.execution.testnet_adapter import TestnetAdapter
    from fbot.gateway.signing import Credentials
    from fbot.gateway.testnet import TestnetClient

    c = TestnetClient(Credentials(api_key="K", api_secret="S"), http=FakeHTTP([ok({"algoId": 1})]))
    a = TestnetAdapter(c, armed=True, symbols={"XUSDT": FILT})
    a.submit(PlaceAlgo("XUSDT", "SELL", "STOP_MARKET", D("99.50"), True, "MARK_PRICE", True, "t0Labc-SL-v1"), now_ms=0)
    _, _, q, _ = c.http.calls[0]
    assert "closePosition=true" in q and "quantity=" not in q and "reduceOnly" not in q
