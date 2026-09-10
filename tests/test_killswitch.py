from fbot.gateway.killswitch import KillSwitch


def test_kill_switch_persists_and_requires_manual_reset(tmp_path):
    ks = KillSwitch(tmp_path / "kill_switch.json")
    assert ks.active is False
    ks.trigger("runaway_orders", now_ns=123, git_sha="abc")
    assert ks.active is True and ks.state["reason"] == "runaway_orders"
    ks2 = KillSwitch(tmp_path / "kill_switch.json")   # restart
    assert ks2.active is True and ks2.state["reason"] == "runaway_orders"
    ks2.reset("elle sıfırlama", now_ns=456)
    assert ks2.active is False
    assert KillSwitch(tmp_path / "kill_switch.json").active is False
    hist = ks2.history()
    assert [h["event"] for h in hist] == ["trigger", "reset"]


def test_trigger_is_idempotent_and_keeps_first_reason(tmp_path):
    ks = KillSwitch(tmp_path / "k.json")
    ks.trigger("a", now_ns=1, git_sha="x"); ks.trigger("b", now_ns=2, git_sha="x")
    assert ks.state["reason"] == "a" and len(ks.history()) == 1
