"""Anahtar değişiminin çalışırken uygulanması (silahlanma denetçisi).

Emir yolunu açıp kapatan bir bileşen olduğu için kuralları sıkı: açık pozisyon varken değişiklik
uygulanmaz, borsa erişimi doğrulanmadan silahlanılmaz, gizli anahtar olaya yazılmaz.
"""
import pytest

from fbot.testnet.arming import ArmingSupervisor


class FakeAdapter:
    def __init__(self):
        self.armed, self.client = False, None

    def rearm(self, client, armed):
        self.client, self.armed = client, armed


def write(p, armed="1", key="k" * 20, sec="s" * 20):
    lines = []
    if armed is not None:
        lines.append(f"FBOT_TESTNET_ARMED={armed}")
    if key is not None:
        lines.append(f"BINANCE_TESTNET_API_KEY={key}")
    if sec is not None:
        lines.append(f"BINANCE_TESTNET_API_SECRET={sec}")
    p.write_text("\n".join(lines) + "\n")
    return p


def mk(tmp_path, probe=lambda c: 1234.5, open_positions=lambda: 0):
    f = tmp_path / ".env"
    sup = ArmingSupervisor(env_path=f, make_client=lambda creds: object(), probe=probe,
                           adapter=FakeAdapter(), open_positions=open_positions, environ={})
    return f, sup


def test_first_check_arms_when_keys_present_and_probe_succeeds(tmp_path):
    f, sup = mk(tmp_path)
    write(f)
    ev = sup.check()
    assert ev["armed"] is True and sup.adapter.armed is True
    assert ev["balance_usdt"] == 1234.5 and ev["kind"] == "arming_changed"


def test_unchanged_file_produces_no_event(tmp_path):
    f, sup = mk(tmp_path)
    write(f)
    assert sup.check() is not None
    assert sup.check() is None and sup.check() is None


def test_new_key_is_applied_without_restart(tmp_path):
    f, sup = mk(tmp_path)
    write(f)
    sup.check()
    first = sup.adapter.client
    write(f, key="y" * 20)
    ev = sup.check()
    assert ev["armed"] is True and sup.adapter.client is not first
    assert ev["masked"] == "…yyyy"


def test_removing_flag_disarms_immediately(tmp_path):
    f, sup = mk(tmp_path)
    write(f)
    sup.check()
    write(f, armed=None)
    ev = sup.check()
    assert ev["armed"] is False and sup.adapter.armed is False
    assert "FBOT_TESTNET_ARMED" in ev["reason"]


def test_probe_failure_leaves_service_disarmed(tmp_path):
    def boom(c):
        raise RuntimeError("HTTP 401 code=-2015 invalid api key")
    f, sup = mk(tmp_path, probe=boom)
    write(f)
    ev = sup.check()
    assert ev["armed"] is False and sup.adapter.armed is False
    assert "-2015" in ev["reason"]


def test_change_is_deferred_while_a_position_is_open(tmp_path):
    f, sup = mk(tmp_path, open_positions=lambda: 1)
    write(f)
    ev = sup.check()
    assert ev["kind"] == "arming_deferred" and sup.adapter.armed is False
    assert sup.check() is None            # aynı gerekçeyle tekrar tekrar olay üretmez


def test_deferred_change_applies_once_position_closes(tmp_path):
    open_n = [1]
    f, sup = mk(tmp_path, open_positions=lambda: open_n[0])
    write(f)
    assert sup.check()["kind"] == "arming_deferred"
    open_n[0] = 0
    assert sup.check()["armed"] is True


def test_event_never_contains_the_secret(tmp_path):
    f, sup = mk(tmp_path)
    write(f, key="abcdefghijklmnop1234", sec="topsecretvalue123456")
    ev = sup.check()
    blob = repr(ev)
    assert "topsecretvalue123456" not in blob and "abcdefghijklmnop1234" not in blob


def test_supervisor_accepts_a_list_of_paths(tmp_path):
    """Servis birden çok anahtar dosyası okur; denetçi liste kabul etmeli."""
    from fbot.gateway.credfile import testnet_paths
    (tmp_path / "data" / "state").mkdir(parents=True)
    write(tmp_path / "data" / "state" / "credentials.env")
    sup = ArmingSupervisor(env_path=testnet_paths(tmp_path), make_client=lambda c: object(), probe=lambda c: 1.0,
                           adapter=FakeAdapter(), open_positions=lambda: 0, environ={})
    assert sup.check()["armed"] is True


def test_testnet_heartbeat_carries_order_and_reconcile_state(tmp_path):
    """Konsol "sistem bağlantı durumu" satırlarını süreç damgasından okur; uydurmaz."""
    from fbot.paper.store import PaperStore
    from fbot.api.paper_view import service_arming
    d = tmp_path / "testnet-x"; d.mkdir()
    s = PaperStore(d / "paper.db", run_id="testnet-x", env="testnet")
    s.heartbeat(now_ns=10**18, detail={"armed": False, "arming_reason": "anahtar yok",
                                       "orders": 3, "fills": 2, "rejected": 1, "reconciled": None})
    s.flush(); s.close()
    out = service_arming(tmp_path, "testnet")
    assert out["armed"] is False and out["reason"] == "anahtar yok"
