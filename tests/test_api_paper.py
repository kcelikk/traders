"""Konsol: paper koşusunu SQLite'tan okur (pozisyon, karar, özet)."""
from pathlib import Path

from fbot.api.paper_view import find_paper_runs, paper_snapshot
from fbot.paper.store import PaperStore


def mk(db, run_id="paper-x", env="paper"):
    s = PaperStore(db, run_id=run_id, env=env)
    s.record_position({"pos_id": "p1", "symbol": "BTCUSDT", "side": "long", "state": "MANAGED", "qty": "0.001", "entry_price": "78000",
                       "sl": "77610", "tp": "78780", "net_pct": "0.21", "exit_reason": None, "opened_ns": 10**18, "closed_ns": None, "entry_state": "S1"})
    s.record_position({"pos_id": "p2", "symbol": "ETHUSDT", "side": "short", "state": "CLOSED", "qty": "0", "entry_price": "2500",
                       "sl": None, "tp": None, "net_pct": "-0.31", "exit_reason": "sl", "opened_ns": 10**18, "closed_ns": 10**18 + 6 * 10**10, "entry_state": "S2"})
    s.record_decision({"n": 1, "t_ms": 1, "symbol": "SOLUSDT", "kind": "REJECT", "reasons": ["K3_warmup"], "cell": "S1/long/15", "explain": "D1"})
    s.record_decision({"n": 2, "t_ms": 2, "symbol": "BTCUSDT", "kind": "APPROVE", "reasons": [], "cell": "S1/long/15", "explain": "D1 · D2 · D3"})
    s.record_order({"seq": 1, "t_ns": 1, "cmd": "PlaceOrder", "symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "qty": "0.001", "client_id": "e1"})
    s.record_fill({"seq": 2, "t_ns": 2, "kind": "entry_fill", "symbol": "BTCUSDT", "price": "78000", "qty": "0.001", "client_id": "e1"})
    s.flush(); s.close()


def test_find_runs_lists_newest_first(tmp_path):
    (tmp_path / "paper-a").mkdir(); (tmp_path / "paper-b").mkdir(); (tmp_path / "rec-x").mkdir()
    mk(tmp_path / "paper-a" / "paper.db", "paper-a")
    mk(tmp_path / "paper-b" / "paper.db", "paper-b")
    runs = find_paper_runs(tmp_path)
    assert [r["run_id"] for r in runs] == ["paper-b", "paper-a"]
    assert all(Path(r["db"]).exists() for r in runs)


def test_snapshot_shapes_positions_decisions_metrics(tmp_path):
    d = tmp_path / "paper-x"; d.mkdir()
    mk(d / "paper.db")
    snap = paper_snapshot(tmp_path)
    assert snap["run_id"] == "paper-x"
    assert len(snap["positions"]) == 2
    p = next(x for x in snap["positions"] if x["pos_id"] == "p1")
    assert p["state"] == "MANAGED" and p["symbol"] == "BTCUSDT" and p["net_pct"] == 0.21 and p["entry_state"] == "S1"
    assert snap["fsm"]["MANAGED"] == 1 and snap["fsm"]["CLOSED"] == 1
    assert snap["exit_reasons"] == {"sl": 1}
    assert len(snap["verdicts"]) == 2 and snap["verdicts"][0]["kind"] == "APPROVE"
    assert snap["metrics"]["işlem"] == 1 and snap["metrics"]["net_toplam_pct"] == -0.31
    assert snap["open_count"] == 1


def test_snapshot_without_any_run_is_empty(tmp_path):
    snap = paper_snapshot(tmp_path)
    assert snap["run_id"] is None and snap["positions"] == [] and snap["open_count"] == 0


def test_environments_are_classified_by_run_id(tmp_path):
    from fbot.api.paper_view import environments
    for name in ("paper-demo-1", "testnet-20260910", "rec-72h"):
        (tmp_path / name).mkdir()
    mk(tmp_path / "paper-demo-1" / "paper.db", "paper-demo-1")
    mk(tmp_path / "testnet-20260910" / "paper.db", "testnet-20260910", env="testnet")
    envs = environments(tmp_path)
    kinds = {e["run_id"]: e["env"] for e in envs}
    assert kinds == {"paper-demo-1": "paper", "testnet-20260910": "testnet"}
    tn = next(e for e in envs if e["env"] == "testnet")
    assert tn["positions"] == 2 and tn["open"] == 1 and "metrics" in tn


def test_snapshot_can_select_specific_run(tmp_path):
    for name in ("paper-a", "testnet-b"):
        (tmp_path / name).mkdir()
        mk(tmp_path / name / "paper.db", name, env=("testnet" if name.startswith("testnet") else "paper"))
    snap = paper_snapshot(tmp_path, run_id="testnet-b")
    assert snap["run_id"] == "testnet-b" and snap["env"] == "testnet"
    assert paper_snapshot(tmp_path)["env"] in ("paper", "testnet")


def test_unknown_run_falls_back_to_newest(tmp_path):
    (tmp_path / "paper-a").mkdir()
    mk(tmp_path / "paper-a" / "paper.db", "paper-a")
    assert paper_snapshot(tmp_path, run_id="yok")["run_id"] == "paper-a"


def _many(db, n_closed=80):
    """Çok sayıda kapanmış pozisyon + eski bir açık pozisyon: LIMIT açık pozisyonu gizlememeli (F06)."""
    s = PaperStore(db, run_id="paper-many", env="paper")
    s.record_position({"pos_id": "open-old", "symbol": "BTCUSDT", "side": "long", "state": "MANAGED", "qty": "0.001",
                       "entry_price": "78000", "sl": None, "tp": None, "net_pct": "0.1", "exit_reason": None,
                       "opened_ns": 1, "closed_ns": None, "entry_state": "S1", "filled_qty": "0.001"})
    for i in range(n_closed):
        s.record_position({"pos_id": f"c{i}", "symbol": "ETHUSDT", "side": "short", "state": "CLOSED", "qty": "0",
                           "entry_price": "2500", "sl": None, "tp": None, "net_pct": "-0.1", "exit_reason": "sl",
                           "opened_ns": 1000 + i, "closed_ns": 2000 + i, "entry_state": "S2",
                           "exit_price": "2510", "filled_qty": "0.04"})
    s.flush(); s.close()


def test_open_positions_are_never_truncated_by_the_limit(tmp_path):
    d = tmp_path / "paper-many"; d.mkdir()
    _many(d / "paper.db")
    snap = paper_snapshot(tmp_path)
    assert any(p["pos_id"] == "open-old" for p in snap["open_positions"])
    assert snap["open_count"] == 1
    assert len(snap["positions"]) <= 50


def test_closed_positions_carry_exit_price_and_filled_qty(tmp_path):
    d = tmp_path / "paper-many"; d.mkdir()
    _many(d / "paper.db", n_closed=3)
    snap = paper_snapshot(tmp_path)
    c = next(p for p in snap["positions"] if p["state"] == "CLOSED")
    assert c["exit_price"] == "2510" and c["filled_qty"] == "0.04"
    o = snap["open_positions"][0]
    assert o["notional_usdt"] == 78.0         # gerçek miktar × giriş fiyatı, sabit 80 değil
    assert snap["gross_exposure_usdt"] == 78.0


def test_effective_config_is_served_when_present(tmp_path):
    d = tmp_path / "paper-cfg"; d.mkdir()
    s = PaperStore(d / "paper.db", run_id="paper-cfg", env="paper")
    s.set_config({"core": {"risk": {"beta_cap_usdt": "750"}}}, config_hash="deadbeef")
    s.flush(); s.close()
    snap = paper_snapshot(tmp_path)
    assert snap["config"]["core"]["risk"]["beta_cap_usdt"] == "750"
    assert snap["config_hash"] == "deadbeef"


def test_requested_run_missing_is_reported_not_silently_swapped(tmp_path):
    d = tmp_path / "paper-x"; d.mkdir()
    mk(d / "paper.db")
    snap = paper_snapshot(tmp_path, run_id="yok-boyle-bir-kosu")
    assert snap["requested_run_id"] == "yok-boyle-bir-kosu" and snap["run_missing"] is True
    assert snap["run_id"] == "paper-x"


def test_old_db_without_new_columns_is_still_readable(tmp_path):
    """Çalışan bir koşunun veritabanı eski şemada olabilir; konsol çökmemeli."""
    import sqlite3
    d = tmp_path / "paper-old"; d.mkdir()
    con = sqlite3.connect(d / "paper.db")
    con.executescript(
        "CREATE TABLE positions (pos_id TEXT PRIMARY KEY, run_id TEXT, symbol TEXT, side TEXT, state TEXT, qty TEXT,"
        " entry_price TEXT, sl TEXT, tp TEXT, net_pct TEXT, exit_reason TEXT, opened_ns INTEGER, closed_ns INTEGER, entry_state TEXT);"
        "CREATE TABLE decisions (id INTEGER PRIMARY KEY, run_id TEXT, n INTEGER, t_ms INTEGER, symbol TEXT, kind TEXT, reasons TEXT, cell TEXT, explain TEXT);"
        "CREATE TABLE orders (id INTEGER PRIMARY KEY); CREATE TABLE fills (id INTEGER PRIMARY KEY);"
        "CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);"
        "INSERT INTO positions VALUES ('p1','r','BTCUSDT','long','MANAGED','0.001','78000',NULL,NULL,'0.2',NULL,1,NULL,'S1');")
    con.commit(); con.close()
    snap = paper_snapshot(tmp_path)
    assert snap["open_positions"][0]["pos_id"] == "p1"
    assert snap["open_positions"][0]["exit_price"] is None
    assert snap["gross_exposure_usdt"] == 78.0


def test_zero_quantity_reports_unknown_notional_not_zero(tmp_path):
    """Eski kayıtta kapanan pozisyonun miktarı 0'a düşer; 0 USDT maruziyet yazmak yanlış (F07)."""
    from fbot.api.paper_view import _notional
    assert _notional({"qty": "0", "entry_price": "100"}) is None
    assert _notional({"qty": "0", "filled_qty": "0.5", "entry_price": "100"}) == 50.0
    assert _notional({"qty": "0.5", "entry_price": None}) is None


def test_service_arming_reports_what_the_testnet_process_last_wrote(tmp_path):
    """Konsol, anahtarın servise ulaşıp ulaşmadığını süreç damgasından okur."""
    from fbot.api.paper_view import service_arming
    assert service_arming(tmp_path, "testnet") == {"run_id": None, "armed": None, "age_s": None, "reason": "koşu yok"}
    d = tmp_path / "testnet-x"; d.mkdir()
    s = PaperStore(d / "paper.db", run_id="testnet-x", env="testnet")
    s.heartbeat(now_ns=10**18, detail={"armed": True, "arming_reason": "anahtar …abcd"})
    s.flush(); s.close()
    out = service_arming(tmp_path, "testnet")
    assert out["armed"] is True and out["run_id"] == "testnet-x" and out["reason"] == "anahtar …abcd"
    assert out["age_s"] is not None


def test_environments_carry_heartbeat_for_the_topology_view(tmp_path):
    """Topoloji ekranı her sürecin canlılığını ortam listesinden okur."""
    from fbot.api.paper_view import environments
    d = tmp_path / "testnet-t"; d.mkdir()
    s = PaperStore(d / "paper.db", run_id="testnet-t", env="testnet")
    s.heartbeat(now_ns=10**18, detail={"armed": True, "reconciled": True, "orders": 4})
    s.flush(); s.close()
    e = environments(tmp_path)[0]
    assert e["env"] == "testnet" and e["heartbeat"]["detail"]["orders"] == 4
    assert e["heartbeat"]["ts_ns"] == 10**18
