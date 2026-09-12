"""Re-baseline raporu (Gate 4e): giriş farkı sıfır olmalı, çıkış farkı raporlanmalı."""
from scripts.rebaseline_report import collect, diff


def base():
    return {"run_dir": "x", "events": 10, "commands": 2, "shadow_commands": 0,
            "by_kind": {"PlaceOrder": 1, "PlaceAlgo": 1},
            "rows": [
                {"seq": 5, "cmd": "PlaceOrder", "symbol": "XUSDT", "client_id": "e1", "reduce_only": False, "qty": "1"},
                {"seq": 6, "cmd": "PlaceAlgo", "symbol": "XUSDT", "client_algo_id": "e1-SL-v1", "trigger_price": "99.51995"},
            ]}


def test_identical_runs_report_no_difference():
    r = diff(base(), base())
    assert r["commands_added"] == r["commands_removed"] == r["commands_changed"] == 0
    assert r["entry_delta_sifir_mi"] is True


def test_rounding_change_shows_as_a_field_diff_not_a_new_command():
    new = base()
    new["rows"][1]["trigger_price"] = "99.51"
    r = diff(base(), new)
    assert r["commands_changed"] == 1 and r["commands_added"] == 0
    assert r["changed_fields"] == {"PlaceAlgo.trigger_price": 1}
    assert r["entry_delta_sifir_mi"] is True, "yuvarlama girişi değiştirmez"


def test_an_extra_entry_is_flagged_as_a_bug_not_a_rebaseline():
    """Giriş kararı farkı sıfır olmalı: fark varsa bu bir bug'dır."""
    new = base()
    new["rows"].append({"seq": 9, "cmd": "PlaceOrder", "symbol": "YUSDT", "client_id": "e2",
                        "reduce_only": False, "qty": "2"})
    r = diff(base(), new)
    assert r["entry_delta"]["eklenen"] == 1 and r["entry_delta_sifir_mi"] is False
    assert "YUSDT" in r["etkilenen_sembol"]


def test_an_extra_exit_is_reported_but_does_not_fail_the_gate():
    new = base()
    new["rows"].append({"seq": 9, "cmd": "PlaceOrder", "symbol": "XUSDT", "client_id": "e1-X-v1",
                        "reduce_only": True, "qty": "1"})
    r = diff(base(), new)
    assert r["commands_added"] == 1 and r["entry_delta_sifir_mi"] is True


def test_real_fixture_round_trip_is_stable():
    a = collect(__import__("pathlib").Path("tests/fixtures/rec-mini"), max_files=1)
    b = collect(__import__("pathlib").Path("tests/fixtures/rec-mini"), max_files=1)
    r = diff(a, b)
    assert r["commands_changed"] == 0 and a["commands"] == b["commands"] > 0


def test_shadow_commands_are_counted_separately():
    a, b = base(), base()
    b["shadow_commands"] = 7
    assert diff(a, b)["shadow"] == {"eski": 0, "yeni": 7}
