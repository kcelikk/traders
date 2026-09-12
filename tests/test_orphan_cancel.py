"""Sahipsiz koruma emri temizliği (Gate 3, adım 5): **dry-run varsayılan**, yalnız bizim emirlerimiz.

Testnet hesabında bize ait olmayan iki koruma emri duruyor (`docs/PHASE.md` denetim tablosu).
Bunlara dokunmak borsada bizim olmayan bir değişikliktir; kural bu yüzden gramer eşleşmesine bağlı.
"""
from decimal import Decimal as D

from fbot.core.commands import CancelAlgo
from fbot.core.ids import algo_cid, entry_cid
from fbot.core.reconcile import ExchangeSnapshot, is_ours, reconcile
from fbot.execution.exchange_state import ReconcileSupervisor

POS = entry_cid("t0", "BTCUSDT", 1789200000000, "long")
OURS = algo_cid(POS, "SL", 1)
FOREIGN = "ios_abc123def456"                      # elle ya da başka araçla konmuş
TAGS = {"t0"}


def snap(algos):
    return ExchangeSnapshot(positions={}, open_algos=algos, open_orders={}, leverage={}, position_mode="ONE_WAY")


def test_ownership_rule_matches_only_our_grammar():
    assert is_ours(OURS, TAGS)
    assert not is_ours(FOREIGN, TAGS)
    assert not is_ours("t0Labc-XX-v1", TAGS)       # rol SL/TP değil
    assert not is_ours("p0Labc-SL-v1", TAGS)       # başka ortamın öneki (paper)
    assert not is_ours(OURS, set())                # etiket verilmediyse sahiplenme yok


def test_orphan_of_ours_produces_a_cancel_action():
    r = reconcile({"positions": {}}, snap({"BTCUSDT": {OURS}}), {}, TAGS)
    assert r.actions == [CancelAlgo("BTCUSDT", OURS)]
    assert any("algo_orphan" in m for m in r.mismatches)
    assert r.foreign == []


def test_foreign_orphan_is_reported_but_never_cancelled():
    r = reconcile({"positions": {}}, snap({"BTCUSDT": {FOREIGN}}), {}, TAGS)
    assert r.actions == [] and r.foreign == [f"BTCUSDT:{FOREIGN}"]
    assert any("algo_orphan" in m for m in r.mismatches), "yabancı emir yine de mutabakatı kilitler"


def test_without_tags_nothing_is_cancelled():
    """Fail-closed: sahibini bilmediğimiz emre dokunulmaz."""
    r = reconcile({"positions": {}}, snap({"BTCUSDT": {OURS, FOREIGN}}), {})
    assert r.actions == [] and len(r.foreign) == 2


class FakeClient:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.cancels = []

    def signed(self, method, path, params, now_ms):
        return {"dualSidePosition": False}

    def positions(self, now_ms):
        return []

    def open_orders(self, now_ms):
        return []

    def open_algos(self, now_ms):
        return [{"symbol": s, "clientAlgoId": a, "algoStatus": "NEW"}
                for s, ids in self.snapshot.items() for a in ids]

    def cancel_algo(self, params, now_ms):
        self.cancels.append(params)
        return {}


def supervisor(client, mode):
    return ReconcileSupervisor(client=client, symbols={"BTCUSDT"}, positions=lambda: {},
                               expected_leverage={}, strategy_tags=TAGS, orphan_cancel=mode)


def test_dry_run_plans_but_does_not_touch_the_exchange():
    c = FakeClient({"BTCUSDT": {OURS}})
    ev = supervisor(c, "dry_run").check(now_ms=1)
    oc = ev["orphan_cancel"]
    assert oc["mode"] == "dry_run" and oc["planned"] and oc["applied"] == []
    assert c.cancels == [], "dry-run borsaya istek göndermemeli"
    assert ev["reconciled"] is False


def test_apply_mode_cancels_only_our_orphans():
    c = FakeClient({"BTCUSDT": {OURS, FOREIGN}})
    ev = supervisor(c, "apply").check(now_ms=1)
    assert c.cancels == [{"symbol": "BTCUSDT", "clientAlgoId": OURS}]
    assert ev["orphan_cancel"]["applied"][0]["ok"] is True
    assert ev["orphan_cancel"]["foreign_untouched"] == [f"BTCUSDT:{FOREIGN}"]


def test_cancel_failure_is_recorded_not_raised():
    class Boom(FakeClient):
        def cancel_algo(self, params, now_ms):
            raise RuntimeError("-2011 Unknown order sent")
    ev = supervisor(Boom({"BTCUSDT": {OURS}}), "apply").check(now_ms=1)
    applied = ev["orphan_cancel"]["applied"]
    assert applied and applied[0]["ok"] is False and "-2011" in applied[0]["err"]


def test_default_mode_is_dry_run():
    s = ReconcileSupervisor(client=None, symbols=set(), positions=lambda: {}, expected_leverage={})
    assert s.orphan_cancel == "dry_run" and s.strategy_tags == set()
