"""Borsa snapshot'ının çekilmesi ve iç durumla karşılaştırılması (CLAUDE.md mutlak kuralı).

Kural: borsa tek doğruluk kaynağıdır; uyuşmazlıkta trading kilitlenir. Kilit fail-closed olmalı,
yani hata, boş cevap ya da eksik alan da kilitlenmeye yol açmalı.
"""
from decimal import Decimal

import pytest

from fbot.core.reconcile import reconcile
from fbot.execution.exchange_state import SnapshotError, fetch_snapshot, internal_view


class FakeClient:
    def __init__(self, positions=None, orders=None, algos=None, dual=False, fail=None):
        self._pos = positions if positions is not None else []
        self._ord = orders or []
        self._algo = algos or []
        self._dual = dual
        self._fail = fail

    def signed(self, method, path, params, now_ms):
        if self._fail == "mode":
            raise RuntimeError("HTTP 500")
        return {"dualSidePosition": self._dual}

    def positions(self, now_ms):
        if self._fail == "pos":
            raise RuntimeError("HTTP 500")
        return self._pos

    def open_orders(self, now_ms):
        return self._ord

    def open_algos(self, now_ms):
        return self._algo

    def balance(self, now_ms):
        if self._fail == "balance":
            raise RuntimeError("HTTP 500")
        return [{"asset": "USDT", "balance": "4208.4", "availableBalance": "4100.0"}]


def prow(sym, amt, lev=5):
    return {"symbol": sym, "positionAmt": amt, "leverage": str(lev), "positionSide": "BOTH"}


UNIVERSE = {"BTCUSDT", "ETHUSDT"}


def test_snapshot_maps_side_quantity_and_leverage():
    c = FakeClient(positions=[prow("BTCUSDT", "0.002", 10), prow("ETHUSDT", "-0.5", 5), prow("XRPUSDT", "100")])
    s = fetch_snapshot(c, UNIVERSE, now_ms=0)
    assert s.positions == {"BTCUSDT": {"side": "long", "qty": Decimal("0.002")},
                           "ETHUSDT": {"side": "short", "qty": Decimal("0.5")}}
    assert s.leverage == {"BTCUSDT": 10, "ETHUSDT": 5}       # evren dışı sembol alınmaz
    assert s.position_mode == "ONE_WAY"


def test_zero_quantity_rows_are_not_positions():
    c = FakeClient(positions=[prow("BTCUSDT", "0"), prow("ETHUSDT", "0.000")])
    assert fetch_snapshot(c, UNIVERSE, now_ms=0).positions == {}


def test_hedge_mode_is_reported_and_fails_reconcile():
    c = FakeClient(positions=[], dual=True)
    s = fetch_snapshot(c, UNIVERSE, now_ms=0)
    assert s.position_mode == "HEDGE"
    r = reconcile({"positions": {}}, s, {})
    assert not r.ok and any("position_mode" in m for m in r.mismatches)


def test_open_algos_and_orders_are_grouped_by_symbol():
    c = FakeClient(algos=[{"symbol": "BTCUSDT", "clientAlgoId": "a1", "algoStatus": "NEW"},
                          {"symbol": "BTCUSDT", "clientAlgoId": "a2", "algoStatus": "CANCELLED"},
                          {"symbol": "XRPUSDT", "clientAlgoId": "a3", "algoStatus": "NEW"}],
                    orders=[{"symbol": "ETHUSDT", "clientOrderId": "o1"}])
    s = fetch_snapshot(c, UNIVERSE, now_ms=0)
    assert s.open_algos == {"BTCUSDT": {"a1"}}          # iptal edilmiş ve evren dışı olan alınmaz
    assert s.open_orders == {"ETHUSDT": {"o1"}}


def test_exchange_error_raises_rather_than_returning_empty():
    """Boş snapshot dönmek "borsada pozisyon yok" demektir; hata bunu söyleyemez."""
    with pytest.raises(SnapshotError):
        fetch_snapshot(FakeClient(fail="pos"), UNIVERSE, now_ms=0)
    with pytest.raises(SnapshotError):
        fetch_snapshot(FakeClient(fail="mode"), UNIVERSE, now_ms=0)


def test_orphan_protective_order_locks_trading():
    """Testnet hesabında gerçekten bulunan durum: pozisyon yok ama koruma emri var."""
    c = FakeClient(positions=[], algos=[{"symbol": "BTCUSDT", "clientAlgoId": "bizim-degil", "algoStatus": "NEW"}])
    r = reconcile({"positions": {}}, fetch_snapshot(c, UNIVERSE, now_ms=0), {})
    assert not r.ok and r.mismatches == ["algo_orphan:BTCUSDT:bizim-degil"]


def test_matching_state_reconciles_clean():
    c = FakeClient(positions=[prow("BTCUSDT", "0.002", 10)],
                   algos=[{"symbol": "BTCUSDT", "clientAlgoId": "p1-SL-v1", "algoStatus": "NEW"}])
    internal = {"positions": {"p1": {"symbol": "BTCUSDT", "side": "long", "qty": Decimal("0.002"),
                                     "algos": {"p1-SL-v1"}}}}
    r = reconcile(internal, fetch_snapshot(c, UNIVERSE, now_ms=0), {"BTCUSDT": 10})
    assert r.ok and r.mismatches == [] and r.unprotected == []


def test_internal_view_extracts_open_positions_only():
    class P:
        def __init__(self, sym, side, qty, state, algos):
            self.symbol, self.side, self.qty, self.state = sym, side, qty, state
            self.active_algos = algos
            self.sl_price, self.tp_price = Decimal("99"), Decimal("101")   # onarım planı bunları okur

    class S:
        value = "MANAGED"

    class C:
        value = "CLOSED"

    positions = {"p1": P("BTCUSDT", "long", Decimal("1"), S(), {"a"}),
                 "p2": P("ETHUSDT", "short", Decimal("2"), C(), {"b"})}
    v = internal_view(positions)
    assert list(v["positions"]) == ["p1"]
    assert v["positions"]["p1"] == {"symbol": "BTCUSDT", "side": "long", "qty": Decimal("1"), "algos": {"a"},
                                    "sl": Decimal("99"), "tp": Decimal("101")}


class FakeAdapter:
    def __init__(self, armed=True):
        self.armed, self.client = armed, FakeClient()

    def rearm(self, client, armed):
        self.client, self.armed = client, armed


def mk_supervisor(client, positions=None, expected_leverage=None):
    from fbot.execution.exchange_state import ReconcileSupervisor
    return ReconcileSupervisor(client=client, symbols=UNIVERSE,
                               positions=lambda: positions or {},
                               expected_leverage=expected_leverage or {})


def test_supervisor_unlocks_when_everything_matches():
    sup = mk_supervisor(FakeClient(positions=[]))
    ev = sup.check(now_ms=0)
    assert ev["reconciled"] is True and ev["mismatches"] == []


def test_supervisor_locks_on_mismatch_and_names_it():
    c = FakeClient(algos=[{"symbol": "BTCUSDT", "clientAlgoId": "yabanci", "algoStatus": "NEW"}])
    ev = mk_supervisor(c).check(now_ms=0)
    assert ev["reconciled"] is False
    assert ev["mismatches"] == ["algo_orphan:BTCUSDT:yabanci"]


def test_supervisor_locks_when_the_exchange_cannot_be_read():
    ev = mk_supervisor(FakeClient(fail="pos")).check(now_ms=0)
    assert ev["reconciled"] is False and "okunamadı" in ev["reason"]


def test_supervisor_reports_unprotected_positions():
    c = FakeClient(positions=[prow("BTCUSDT", "0.002", 10)])
    ev = mk_supervisor(c).check(now_ms=0)
    assert ev["unprotected"] == ["BTCUSDT"] and ev["reconciled"] is False


def test_disarmed_service_cannot_reconcile_and_stays_locked():
    ev = mk_supervisor(None).check(now_ms=0)
    assert ev["reconciled"] is False and "istemcisi yok" in ev["reason"]


def test_repeated_identical_result_is_not_re_reported():
    sup = mk_supervisor(FakeClient(positions=[]))
    assert sup.check(now_ms=0) is not None
    assert sup.check(now_ms=1) is None          # durum değişmedi → olay üretilmez


class ClockClient(FakeClient):
    """Her isteğin kendi zaman damgasını aldığını doğrular."""

    def __init__(self):
        super().__init__(positions=[])
        self.seen = []

    def signed(self, method, path, params, now_ms):
        self.seen.append(now_ms)
        return {"dualSidePosition": False}

    def positions(self, now_ms):
        self.seen.append(now_ms)
        return []

    def open_orders(self, now_ms):
        self.seen.append(now_ms)
        return []

    def open_algos(self, now_ms):
        self.seen.append(now_ms)
        return []

    def balance(self, now_ms):
        self.seen.append(now_ms)
        return []


def test_each_request_gets_a_fresh_timestamp():
    """Tek damga tüm isteklere paylaştırılınca sonuncular recvWindow'u aşıyor (-1021)."""
    ticks = iter([1000, 2000, 8000, 9000, 10000, 11000])
    c = ClockClient()
    fetch_snapshot(c, UNIVERSE, now_ms=lambda: next(ticks))
    assert c.seen == [1000, 2000, 8000, 9000, 10000, 11000]


def test_fixed_timestamp_still_accepted_for_tests():
    c = ClockClient()
    fetch_snapshot(c, UNIVERSE, now_ms=42)
    assert c.seen == [42, 42, 42, 42, 42, 42]
