"""Maliyet senaryoları: komisyon, spread geçişi ve çıkış türüne göre farklılaşma.

Düzeltilen hata: gidiş-dönüş taker işlemde **bir tam spread** ödenir (her yönde yarım), iki değil.
Eski model iki tam spread yazıyordu ve sonuçları karamsar yönde yanlı yapıyordu.

Maker girişin bilinen sınırı: post-only emir hiç dolmayabilir. Bariyer testi girişin her zaman
gerçekleştiğini varsayar, bu yüzden maker senaryoları **dolum olasılığı bakımından iyimserdir**.
"""
import pytest

from fbot.research.costs import CostScenario, scenarios_from_config


def test_taker_round_trip_pays_one_full_spread():
    s = CostScenario("taker/taker", fee_in_pct=0.05, fee_out_pct=0.05, spread_crossings=2.0)
    assert s.entry_exit_pct(spread_bps=10.0) == pytest.approx(0.10 + 0.10)   # komisyon + 1 tam spread (10 bps = %0,10)


def test_maker_entry_halves_the_spread_cost():
    s = CostScenario("maker/taker", fee_in_pct=0.02, fee_out_pct=0.05, spread_crossings=1.0)
    assert s.entry_exit_pct(spread_bps=10.0) == pytest.approx(0.07 + 0.05)


def test_maker_both_sides_pays_no_spread():
    s = CostScenario("maker/maker", fee_in_pct=0.02, fee_out_pct=0.02, spread_crossings=0.0)
    assert s.entry_exit_pct(spread_bps=10.0) == pytest.approx(0.04)


def test_bnb_discount_applies_to_commission_only():
    a = CostScenario("x", 0.05, 0.05, 2.0)
    b = CostScenario("x+bnb", 0.05, 0.05, 2.0, bnb_discount=True)
    assert b.entry_exit_pct(10.0) == pytest.approx(0.10 * 0.9 + 0.10)
    assert b.entry_exit_pct(0.0) == pytest.approx(a.entry_exit_pct(0.0) * 0.9)


def test_stop_exit_is_always_taker_even_in_maker_scenarios():
    """Koruma emri piyasa emridir; maker olamaz. Senaryo maker dese de stop taker ücreti öder."""
    s = CostScenario("maker/maker", 0.02, 0.02, 0.0, taker_fee_pct=0.05)
    assert s.cost_for("tp", spread_bps=10.0) == pytest.approx(0.04)
    assert s.cost_for("sl", spread_bps=10.0) == pytest.approx(0.02 + 0.05 + 0.05)     # giriş maker, çıkış taker + yarım spread
    assert s.cost_for("timeout", spread_bps=10.0) == pytest.approx(0.02 + 0.05 + 0.05)


def test_taker_scenario_is_uniform_across_exit_reasons():
    s = CostScenario("taker/taker", 0.05, 0.05, 2.0, taker_fee_pct=0.05)
    for reason in ("tp", "sl", "timeout"):
        assert s.cost_for(reason, 10.0) == pytest.approx(0.20)


def test_scenarios_are_read_from_config():
    cfg = {"costs": {"scenarios": [
        {"name": "a", "fee_in_pct": 0.05, "fee_out_pct": 0.05},
        {"name": "b", "fee_in_pct": 0.02, "fee_out_pct": 0.05, "spread_crossings": 1.0, "bnb_discount": True},
    ]}}
    out = scenarios_from_config(cfg)
    assert [s.name for s in out] == ["a", "b"]
    assert out[0].spread_crossings == 2.0        # varsayılan taker/taker
    assert out[1].bnb_discount is True


def test_unknown_scenario_name_is_rejected():
    from fbot.research.costs import pick
    with pytest.raises(KeyError):
        pick([CostScenario("a", 0.05, 0.05, 2.0)], "yok")
