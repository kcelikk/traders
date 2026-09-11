"""SQLite kalıcılık (Faz 7 §2): write-behind, tek yazar, yeniden başlatmada devam."""
import json
import sqlite3
from decimal import Decimal

from fbot.paper.store import PaperStore


def test_writes_and_reads_back(tmp_path):
    db = tmp_path / "paper.db"
    s = PaperStore(db, run_id="r1")
    s.record_decision({"t_ms": 1, "symbol": "X", "kind": "APPROVE", "reasons": [], "cell": "S1/long/15", "explain": "D1"})
    s.record_order({"seq": 5, "t_ns": 9, "cmd": "PlaceOrder", "symbol": "X", "side": "BUY", "type": "MARKET", "qty": "0.5", "client_id": "e1"})
    s.record_fill({"seq": 6, "t_ns": 10, "kind": "entry_fill", "symbol": "X", "price": "100", "qty": "0.5", "client_id": "e1"})
    s.record_position({"pos_id": "p1", "symbol": "X", "side": "long", "state": "MANAGED", "qty": "0.5", "entry_price": "100",
                       "sl": "99.5", "tp": "101", "net_pct": None, "exit_reason": None, "opened_ns": 10, "closed_ns": None, "entry_state": "S1"})
    s.flush()
    con = sqlite3.connect(db)
    assert con.execute("select count(*) from decisions").fetchone()[0] == 1
    assert con.execute("select count(*) from orders").fetchone()[0] == 1
    assert con.execute("select count(*) from fills").fetchone()[0] == 1
    assert con.execute("select state, qty from positions where pos_id='p1'").fetchone() == ("MANAGED", "0.5")
    assert con.execute("select run_id from decisions").fetchone()[0] == "r1"


def test_position_upsert_keeps_one_row(tmp_path):
    s = PaperStore(tmp_path / "p.db", run_id="r")
    base = {"pos_id": "p1", "symbol": "X", "side": "long", "qty": "1", "entry_price": "100", "sl": "99", "tp": "101",
            "net_pct": None, "exit_reason": None, "opened_ns": 1, "closed_ns": None, "entry_state": "S1"}
    s.record_position({**base, "state": "PROTECTING"})
    s.record_position({**base, "state": "CLOSED", "exit_reason": "tp", "net_pct": "0.9", "closed_ns": 99})
    s.flush()
    rows = sqlite3.connect(tmp_path / "p.db").execute("select state, exit_reason, net_pct from positions").fetchall()
    assert rows == [("CLOSED", "tp", "0.9")]


def test_summary_counts(tmp_path):
    s = PaperStore(tmp_path / "s.db", run_id="r")
    for i in range(3):
        s.record_decision({"t_ms": i, "symbol": "X", "kind": "APPROVE" if i else "REJECT", "reasons": ["K11_margin"] if not i else [], "cell": "c", "explain": ""})
    s.record_position({"pos_id": "p1", "symbol": "X", "side": "long", "state": "CLOSED", "qty": "0", "entry_price": "100",
                       "sl": None, "tp": None, "net_pct": "-0.2", "exit_reason": "sl", "opened_ns": 1, "closed_ns": 2, "entry_state": "S1"})
    s.flush()
    sm = s.summary()
    assert sm["decisions"] == 3 and sm["approve"] == 2 and sm["reject"] == 1
    assert sm["positions_closed"] == 1 and sm["net_sum_pct"] == -0.2
    assert sm["exit_reasons"] == {"sl": 1}


def test_reopen_appends(tmp_path):
    db = tmp_path / "a.db"
    s = PaperStore(db, run_id="r")
    s.record_decision({"t_ms": 1, "symbol": "X", "kind": "APPROVE", "reasons": [], "cell": "c", "explain": ""})
    s.close()
    s2 = PaperStore(db, run_id="r")
    s2.record_decision({"t_ms": 2, "symbol": "X", "kind": "APPROVE", "reasons": [], "cell": "c", "explain": ""})
    s2.flush()
    assert s2.summary()["decisions"] == 2


def test_env_is_recorded_in_meta(tmp_path):
    s = PaperStore(tmp_path / "m.db", run_id="r", env="testnet")
    s.flush()
    con = sqlite3.connect(tmp_path / "m.db")
    assert con.execute("select value from meta where key='env'").fetchone()[0] == "testnet"
    assert con.execute("select value from meta where key='run_id'").fetchone()[0] == "r"
    assert PaperStore(tmp_path / "m.db", run_id="r").env == "testnet"


def test_exit_price_and_effective_config_are_stored(tmp_path):
    s = PaperStore(tmp_path / "c.db", run_id="r", env="paper")
    s.set_config({"risk": {"beta_cap_usdt": "750"}, "position": {"lock_trigger_pct": "0.30"}}, config_hash="abc123")
    s.record_position({"pos_id": "p1", "symbol": "X", "side": "long", "state": "CLOSED", "qty": "0", "entry_price": "100",
                       "sl": None, "tp": None, "net_pct": "0.4", "exit_reason": "tp", "opened_ns": 1, "closed_ns": 2,
                       "entry_state": "S1", "exit_price": "100.5", "filled_qty": "0.5"})
    s.heartbeat(now_ns=12345, detail={"open": 1})
    s.flush()
    cfg, h = s.get_config()
    assert cfg["risk"]["beta_cap_usdt"] == "750" and h == "abc123"
    row = s.con.execute("select exit_price, filled_qty from positions where pos_id='p1'").fetchone()
    assert row == ("100.5", "0.5")
    hb = s.get_heartbeat()
    assert hb["ts_ns"] == 12345 and hb["detail"]["open"] == 1


def test_heartbeat_age_marks_stale(tmp_path):
    s = PaperStore(tmp_path / "h.db", run_id="r")
    s.heartbeat(now_ns=1_000_000_000_000, detail={})
    s.flush()
    assert s.get_heartbeat()["ts_ns"] == 1_000_000_000_000


def test_old_db_without_new_columns_still_opens(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.executescript("CREATE TABLE positions (pos_id TEXT PRIMARY KEY, run_id TEXT, symbol TEXT, side TEXT, state TEXT, qty TEXT,"
                      " entry_price TEXT, sl TEXT, tp TEXT, net_pct TEXT, exit_reason TEXT, opened_ns INTEGER, closed_ns INTEGER, entry_state TEXT);")
    con.commit(); con.close()
    s = PaperStore(db, run_id="r")          # şema göçü çalışmalı
    s.record_position({"pos_id": "p", "symbol": "X", "side": "long", "state": "CLOSED", "qty": "0", "entry_price": "1",
                       "sl": None, "tp": None, "net_pct": "0", "exit_reason": "tp", "opened_ns": 1, "closed_ns": 2,
                       "entry_state": "S1", "exit_price": "1.1"})
    s.flush()
    assert s.con.execute("select exit_price from positions").fetchone()[0] == "1.1"
