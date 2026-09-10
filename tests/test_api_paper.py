"""Konsol: paper koşusunu SQLite'tan okur (pozisyon, karar, özet)."""
from pathlib import Path

from fbot.api.paper_view import find_paper_runs, paper_snapshot
from fbot.paper.store import PaperStore


def mk(db, run_id="paper-x"):
    s = PaperStore(db, run_id=run_id)
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
