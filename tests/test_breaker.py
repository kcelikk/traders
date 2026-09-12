"""Devre kesici (Gate 4c): günlük net zarar, ardışık zarar, alarm/enforce ayrımı."""
from decimal import Decimal as D

from fbot.core.breaker import ALARM, DAY_MS, ENFORCE, BreakerConfig, BreakerState, entry_blocked, on_trade

T0 = 1789200000000          # gün ortası bir damga


def st():
    return BreakerState()


def test_alarm_mode_reports_but_changes_no_decision():
    """Ölçmeden kısıtlama koymayız: alarm modu yanlış-pozitif saymak içindir."""
    cfg = BreakerConfig(mode=ALARM, daily_net_loss_usdt=D("10"))
    s = st()
    evs = on_trade(cfg, s, D("-12"), T0)
    assert evs and evs[0]["rule"] == "daily_net_loss" and evs[0]["mode"] == ALARM
    assert entry_blocked(cfg, s) is None


def test_enforce_mode_blocks_new_entries():
    cfg = BreakerConfig(mode=ENFORCE, daily_net_loss_usdt=D("10"))
    s = st()
    on_trade(cfg, s, D("-12"), T0)
    assert entry_blocked(cfg, s) == "daily_net_loss"


def test_limit_is_cumulative_not_per_trade():
    cfg = BreakerConfig(mode=ENFORCE, daily_net_loss_usdt=D("10"))
    s = st()
    assert on_trade(cfg, s, D("-6"), T0) == []
    assert on_trade(cfg, s, D("-5"), T0)[0]["rule"] == "daily_net_loss"


def test_profit_reduces_the_daily_loss():
    cfg = BreakerConfig(mode=ENFORCE, daily_net_loss_usdt=D("10"))
    s = st()
    on_trade(cfg, s, D("-8"), T0)
    on_trade(cfg, s, D("5"), T0)
    assert on_trade(cfg, s, D("-6"), T0) == [], "net -9: eşik aşılmadı"
    assert entry_blocked(cfg, s) is None


def test_each_rule_fires_once_per_day():
    cfg = BreakerConfig(mode=ENFORCE, daily_net_loss_usdt=D("10"))
    s = st()
    on_trade(cfg, s, D("-12"), T0)
    assert on_trade(cfg, s, D("-3"), T0) == [], "aynı kural gün içinde tekrar olay üretmez"


def test_new_utc_day_resets_the_counters():
    cfg = BreakerConfig(mode=ENFORCE, daily_net_loss_usdt=D("10"))
    s = st()
    on_trade(cfg, s, D("-12"), T0)
    assert entry_blocked(cfg, s)
    on_trade(cfg, s, D("-1"), T0 + DAY_MS)
    assert entry_blocked(cfg, s) is None and s.day_net_usdt == D("-1")


def test_consecutive_losses_reset_on_a_win():
    cfg = BreakerConfig(mode=ENFORCE, consecutive_loss_limit=3)
    s = st()
    for _ in range(2):
        on_trade(cfg, s, D("-1"), T0)
    on_trade(cfg, s, D("0.5"), T0)
    assert s.consecutive_losses == 0 and entry_blocked(cfg, s) is None
    for _ in range(3):
        evs = on_trade(cfg, s, D("-1"), T0)
    assert evs[0]["rule"] == "consecutive_loss" and entry_blocked(cfg, s) == "consecutive_loss"


def test_break_even_trade_is_not_a_loss():
    cfg = BreakerConfig(mode=ENFORCE, consecutive_loss_limit=2)
    s = st()
    on_trade(cfg, s, D("-1"), T0)
    on_trade(cfg, s, D("0"), T0)
    assert s.consecutive_losses == 0


def test_no_limits_configured_means_no_blocking():
    cfg = BreakerConfig(mode=ENFORCE)
    s = st()
    assert on_trade(cfg, s, D("-1000"), T0) == [] and entry_blocked(cfg, s) is None


def test_day_boundary_uses_the_exchange_timestamp_not_the_local_clock():
    """İş mantığı sistem saatini okumaz (Rule Zero #2)."""
    s = st()
    assert s.day_of(T0) % DAY_MS == 0 and s.day_of(T0 + DAY_MS) - s.day_of(T0) == DAY_MS


# ---- canlı yola bağlanışı: 418 ve arıza dedektörü kalıcı kill switch tetikler
def test_runaway_and_ban_reach_the_kill_switch(tmp_path, monkeypatch):
    """İkisi de bugüne kadar ölü yoldu: RunawayDetector hiç kurulmuyordu, 418 yalnız hata metnine
    yazılıyordu."""
    from fbot.gateway.killswitch import KillSwitch

    ks = KillSwitch(tmp_path / "kill.json")
    assert not ks.active
    ks.trigger("runaway:runaway_rejects", now_ns=1, git_sha="abc")
    assert ks.active and ks.state["reason"].startswith("runaway:")
    ks.trigger("http_418_ban", now_ns=2, git_sha="abc")
    assert ks.state["reason"] == "runaway:runaway_rejects", "ilk neden korunur"
    assert KillSwitch(tmp_path / "kill.json").active, "restart'ı hayatta kalır"


def test_runaway_detector_counts_rejects_and_orders():
    from fbot.core.risk import RunawayDetector

    d = RunawayDetector(window_ms=60_000, max_orders=3, max_consecutive_rejects=2)
    assert d.on_order(1000) is None and d.on_order(2000) is None and d.on_order(3000) is None
    assert d.on_order(4000) == "runaway_orders"
    d2 = RunawayDetector(window_ms=60_000, max_orders=99, max_consecutive_rejects=2)
    assert d2.on_reject(1) is None
    assert d2.on_reject(2) == "runaway_rejects"
    d2.on_ack(3)
    assert d2.on_reject(4) is None, "başarılı emir ardışık sayacı sıfırlar"


def test_orders_outside_the_window_do_not_count():
    from fbot.core.risk import RunawayDetector

    d = RunawayDetector(window_ms=1_000, max_orders=2, max_consecutive_rejects=99)
    d.on_order(0)
    d.on_order(100)
    assert d.on_order(5_000) is None, "pencere dışındaki emirler düşer"
