"""Maliyet sürüklenmesi alarmı (prompt BÖLÜM 6.4). Saf; işlem engellemez, alarm üretir."""
from decimal import Decimal as D

from fbot.core.cost_drift import CostDriftConfig, CostDriftMonitor

CFG = CostDriftConfig(window_ms=3_600_000, capital_usdt=D("1000"),
                      commission_to_gross_max=D("0.30"), cost_to_capital_max=D("0.02"), net_per_trade_min=D("-0.05"))


def trade(net_pct, commission=D("0.08"), funding=D("0"), slippage=D("0"), notional=D("80")):
    return {"net_pct": D(str(net_pct)), "commission_usdt": commission, "funding_usdt": funding,
            "slippage_usdt": slippage, "notional": notional}


def test_no_alarm_when_within_thresholds():
    m = CostDriftMonitor(CFG)
    for i in range(10):
        assert m.on_trade(trade("0.5"), now_ms=i * 1000) == []
    r = m.report(now_ms=10_000)
    assert r["trades"] == 10 and r["commission_to_gross"] is not None and r["alarms"] == []


def test_commission_to_gross_alarm():
    """Brüt kârın çoğu komisyona gidiyorsa alarm."""
    m = CostDriftMonitor(CFG)
    for i in range(20):
        m.on_trade(trade("0.02"), now_ms=i * 1000)     # brüt küçük, komisyon sabit
    r = m.report(now_ms=20_000)
    assert "commission_to_gross" in r["alarms"] and r["commission_to_gross"] > CFG.commission_to_gross_max


def test_cost_to_capital_alarm():
    m = CostDriftMonitor(CFG)
    for i in range(300):
        m.on_trade(trade("0.1"), now_ms=i * 1000)      # 300 × 0.08 = 24 USDT > 1000 × %2
    r = m.report(now_ms=300_000)
    assert "cost_to_capital" in r["alarms"]


def test_net_per_trade_alarm():
    m = CostDriftMonitor(CFG)
    for i in range(30):
        m.on_trade(trade("-0.12"), now_ms=i * 1000)
    r = m.report(now_ms=30_000)
    assert "net_per_trade" in r["alarms"] and r["net_per_trade_pct"] < CFG.net_per_trade_min


def test_window_slides_old_trades_drop_out():
    m = CostDriftMonitor(CFG)
    for i in range(30):
        m.on_trade(trade("-0.5"), now_ms=i * 1000)
    assert m.report(now_ms=30_000)["trades"] == 30
    assert m.report(now_ms=30_000 + CFG.window_ms + 1)["trades"] == 0


def test_alarm_is_emitted_once_per_breach_not_every_trade():
    m = CostDriftMonitor(CFG)
    out = []
    for i in range(40):
        out += m.on_trade(trade("-0.2"), now_ms=i * 1000)
    kinds = [a.kind for a in out]
    assert kinds.count("cost_drift:net_per_trade") == 1, kinds
    # eşik altına dönünce yeniden alarm verebilir (pencere kaymalı: kazançlar dışarı düşmeli)
    for i in range(200):
        out += m.on_trade(trade("1.0"), now_ms=100_000 + i * 1000)
    for i in range(60):
        out += m.on_trade(trade("-0.3"), now_ms=4_000_000 + i * 1000)
    assert [a.kind for a in out].count("cost_drift:net_per_trade") == 2


def test_alarm_carries_numbers_for_operator():
    m = CostDriftMonitor(CFG)
    alarms = []
    for i in range(30):
        alarms += m.on_trade(trade("-0.3"), now_ms=i * 1000)
    a = next(x for x in alarms if x.kind.endswith("net_per_trade"))
    assert "eşik" in a.detail and "-0.3" in a.detail


def test_no_alarm_without_enough_trades():
    m = CostDriftMonitor(CostDriftConfig(**{**CFG.__dict__, "min_trades": 50}))
    out = []
    for i in range(20):
        out += m.on_trade(trade("-5.0"), now_ms=i * 1000)
    assert out == [] and m.report(now_ms=20_000)["alarms"] == []
