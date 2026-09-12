"""Gate 3 kalanları: bakiye/teminat snapshot'ı, HEDGE'te emir yolunun kapanması, koruma onarımı."""
from decimal import Decimal as D

from fbot.core.ids import algo_cid, entry_cid
from fbot.core.reconcile import ExchangeSnapshot, reconcile
from fbot.execution.exchange_state import ReconcileSupervisor, fetch_snapshot

POS = entry_cid("t0", "BTCUSDT", 1789200000000, "long")
UNIVERSE = {"BTCUSDT", "ETHUSDT"}


class Client:
    def __init__(self, dual=False, positions=None, algos=None, balance=None):
        self.dual, self._pos, self._algos = dual, positions or [], algos or []
        self._balance = balance if balance is not None else [{"asset": "USDT", "balance": "4208.4", "availableBalance": "4100.0"}]
        self.algo_calls = []

    def signed(self, m, p, params, now_ms):
        return {"dualSidePosition": self.dual}

    def positions(self, now_ms):
        return self._pos

    def open_orders(self, now_ms):
        return []

    def open_algos(self, now_ms):
        return self._algos

    def balance(self, now_ms):
        return self._balance

    def place_algo(self, params, now_ms):
        self.algo_calls.append(params)
        return {"algoId": 1, "algoStatus": "NEW"}


def prow(sym, amt, lev=10, maint="1.2", initial="8.0"):
    return {"symbol": sym, "positionAmt": amt, "leverage": str(lev), "positionSide": "BOTH",
            "maintMargin": maint, "initialMargin": initial}


def test_snapshot_carries_balance_and_margin():
    """Bakiye iç muhasebeden değil borsadan gelir (CLAUDE.md: borsa tek doğruluk kaynağı)."""
    snap = fetch_snapshot(Client(positions=[prow("BTCUSDT", "0.002")]), UNIVERSE, now_ms=1)
    assert snap.balance == {"wallet": D("4208.4"), "available": D("4100.0")}
    assert snap.margin["BTCUSDT"] == {"maint": D("1.2"), "initial": D("8.0")}


def test_unreadable_balance_is_fail_closed():
    class Boom(Client):
        def balance(self, now_ms):
            raise RuntimeError("HTTP 500")
    from fbot.execution.exchange_state import SnapshotError
    try:
        fetch_snapshot(Boom(), UNIVERSE, now_ms=1)
        raise AssertionError("bakiye okunamadığı hâlde snapshot döndü")
    except SnapshotError as e:
        assert "okunamadı" in str(e)


def test_hedge_mode_blocks_the_order_path_not_only_the_lock():
    """HEDGE'te `positionSide` semantiği değişir. Yalnız `reconciled=False` yapmak yetmez:
    K2 girişleri durdurur ama koruma ve çıkış emirleri yine gider."""
    blocked = []
    sup = ReconcileSupervisor(client=Client(dual=True), symbols=UNIVERSE, positions=lambda: {},
                              expected_leverage={}, on_arm_block=blocked.append)
    ev = sup.check(now_ms=1)
    assert ev["reconciled"] is False and ev["arm_block"] and "ONE-WAY" in ev["arm_block"]
    assert blocked and "HEDGE" in blocked[0]


def test_one_way_mode_does_not_block():
    blocked = []
    sup = ReconcileSupervisor(client=Client(dual=False), symbols=UNIVERSE, positions=lambda: {},
                              expected_leverage={}, on_arm_block=blocked.append)
    ev = sup.check(now_ms=1)
    assert ev["arm_block"] is None and blocked == []


def test_balance_is_published_to_the_account_view():
    seen = []
    sup = ReconcileSupervisor(client=Client(), symbols=UNIVERSE, positions=lambda: {},
                              expected_leverage={}, on_balance=seen.append)
    sup.check(now_ms=1)
    assert seen and seen[0]["available"] == D("4100.0")


def _pos_obj(sl=D("99"), tp=D("101")):
    class P:
        symbol, side, qty = "BTCUSDT", "long", D("0.002")
        active_algos: set = set()
        sl_price, tp_price = sl, tp

        class state:
            value = "MANAGED"
    return {POS: P()}


def test_unprotected_known_position_produces_a_repair_plan():
    snap = ExchangeSnapshot(positions={"BTCUSDT": {"side": "long", "qty": D("0.002")}}, open_algos={},
                            open_orders={}, leverage={}, position_mode="ONE_WAY")
    internal = {"positions": {POS: {"symbol": "BTCUSDT", "side": "long", "qty": D("0.002"),
                                    "algos": set(), "sl": D("99"), "tp": D("101")}}}
    r = reconcile(internal, snap, {})
    assert r.unprotected == ["BTCUSDT"]
    roles = {rp["role"]: rp for rp in r.repairs}
    assert set(roles) == {"SL", "TP"}
    assert roles["SL"]["trigger_price"] == "99" and roles["SL"]["side"] == "SELL"


def test_unknown_position_gets_no_invented_protection():
    """Borsada olup bizde olmayan pozisyona koruma seviyesi uydurulmaz; durum kilitli kalır."""
    snap = ExchangeSnapshot(positions={"BTCUSDT": {"side": "long", "qty": D("0.002")}}, open_algos={},
                            open_orders={}, leverage={}, position_mode="ONE_WAY")
    r = reconcile({"positions": {}}, snap, {})
    assert r.unprotected == ["BTCUSDT"] and r.repairs == []
    assert any("position_unknown" in m for m in r.mismatches)


def test_repair_is_dry_run_by_default():
    c = Client(positions=[prow("BTCUSDT", "0.002")])
    sup = ReconcileSupervisor(client=c, symbols=UNIVERSE, positions=_pos_obj, expected_leverage={})
    ev = sup.check(now_ms=1)
    assert ev["protect_repair"]["mode"] == "dry_run" and ev["protect_repair"]["planned"]
    assert ev["protect_repair"]["applied"] == [] and c.algo_calls == []


def test_repair_in_apply_mode_places_protection_with_position_side():
    c = Client(positions=[prow("BTCUSDT", "0.002")])
    sup = ReconcileSupervisor(client=c, symbols=UNIVERSE, positions=_pos_obj, expected_leverage={},
                              protect_repair="apply")
    ev = sup.check(now_ms=1)
    assert len(c.algo_calls) == 2 and sup.repaired == 2
    sl = next(p for p in c.algo_calls if p["type"] == "STOP_MARKET")
    assert sl["positionSide"] == "BOTH" and sl["closePosition"] == "true" and sl["triggerPrice"] == "99"
    assert all(a["ok"] for a in ev["protect_repair"]["applied"])


def test_multi_asset_margin_is_reported_and_sizing_stays_conservative():
    """Testnet hesabında ölçüldü: çoklu varlık modu açıkken `availableBalance` USDT dışı bakiyeyi
    de içeriyor (USDT cüzdan 4208, available 9892; fark USDC'den). Kilitli kararlar USDT büyüklüğü
    varsaydığı için büyüklük hesabında iki değerin küçüğü kullanılır."""
    class Multi(Client):
        def signed(self, m, p, params, now_ms):
            if p.endswith("multiAssetsMargin"):
                return {"multiAssetsMargin": True}
            return {"dualSidePosition": False}

    seen = []
    c = Multi(balance=[{"asset": "USDT", "balance": "4208.4", "availableBalance": "9892.5"}])
    sup = ReconcileSupervisor(client=c, symbols=UNIVERSE, positions=lambda: {}, expected_leverage={},
                              on_balance=seen.append)
    ev = sup.check(now_ms=1)
    assert ev["multi_assets_margin"] is True
    assert ev["balance"]["available"] == "9892.5", "ham değer olduğu gibi raporlanır"
    assert seen[0]["available"] == D("4208.4") and seen[0]["multi_assets_capped"] is True


def test_single_asset_margin_passes_the_available_balance_through():
    seen = []
    sup = ReconcileSupervisor(client=Client(), symbols=UNIVERSE, positions=lambda: {},
                              expected_leverage={}, on_balance=seen.append)
    ev = sup.check(now_ms=1)
    assert ev["multi_assets_margin"] is None
    assert seen[0]["available"] == D("4100.0") and "multi_assets_capped" not in seen[0]
