"""Paper kalıcılık: SQLite (stdlib), write-behind tampon, tek yazar. I/O kenarı.

Hot path'te değildir: çekirdek komut üretir, buradaki kayıt görünüm ve rapor içindir (docs/design/faz7-paper-trading.md §2).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, run_id TEXT, t_ms INTEGER, symbol TEXT, kind TEXT, reasons TEXT, cell TEXT, explain TEXT);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, run_id TEXT, seq INTEGER, t_ns INTEGER, cmd TEXT, symbol TEXT, side TEXT, type TEXT, qty TEXT, client_id TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY, run_id TEXT, seq INTEGER, t_ns INTEGER, kind TEXT, symbol TEXT, price TEXT, qty TEXT, client_id TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS positions (pos_id TEXT PRIMARY KEY, run_id TEXT, symbol TEXT, side TEXT, state TEXT, qty TEXT, entry_price TEXT,
                                      sl TEXT, tp TEXT, net_pct TEXT, exit_reason TEXT, opened_ns INTEGER, closed_ns INTEGER, entry_state TEXT);
CREATE INDEX IF NOT EXISTS ix_dec_t ON decisions(t_ms);
CREATE INDEX IF NOT EXISTS ix_pos_state ON positions(state);
"""


class PaperStore:
    def __init__(self, path: Path, run_id: str, flush_every: int = 200):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.flush_every = flush_every
        self.con = sqlite3.connect(str(self.path), check_same_thread=False)
        self.con.executescript(SCHEMA)
        self.con.commit()
        self.pending = 0

    # ---- yazımlar (tamponlu)
    def record_decision(self, d: dict) -> None:
        self.con.execute("INSERT INTO decisions(run_id,t_ms,symbol,kind,reasons,cell,explain) VALUES(?,?,?,?,?,?,?)",
                         (self.run_id, d.get("t_ms"), d.get("symbol"), d.get("kind"), json.dumps(d.get("reasons") or []), d.get("cell"), d.get("explain")))
        self._maybe_flush()

    def record_order(self, o: dict) -> None:
        self.con.execute("INSERT INTO orders(run_id,seq,t_ns,cmd,symbol,side,type,qty,client_id,payload) VALUES(?,?,?,?,?,?,?,?,?,?)",
                         (self.run_id, o.get("seq"), o.get("t_ns"), o.get("cmd"), o.get("symbol"), o.get("side"), o.get("type"),
                          o.get("qty"), o.get("client_id") or o.get("client_algo_id"), json.dumps(o, default=str)))
        self._maybe_flush()

    def record_fill(self, f: dict) -> None:
        self.con.execute("INSERT INTO fills(run_id,seq,t_ns,kind,symbol,price,qty,client_id,reason) VALUES(?,?,?,?,?,?,?,?,?)",
                         (self.run_id, f.get("seq"), f.get("t_ns"), f.get("kind"), f.get("symbol"), f.get("price"), f.get("qty"),
                          f.get("client_id"), f.get("reason")))
        self._maybe_flush()

    def record_position(self, p: dict) -> None:
        self.con.execute("""INSERT INTO positions(pos_id,run_id,symbol,side,state,qty,entry_price,sl,tp,net_pct,exit_reason,opened_ns,closed_ns,entry_state)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(pos_id) DO UPDATE SET state=excluded.state, qty=excluded.qty, sl=excluded.sl, tp=excluded.tp,
                            net_pct=excluded.net_pct, exit_reason=excluded.exit_reason, closed_ns=excluded.closed_ns""",
                         (p["pos_id"], self.run_id, p.get("symbol"), p.get("side"), p.get("state"), p.get("qty"), p.get("entry_price"),
                          p.get("sl"), p.get("tp"), p.get("net_pct"), p.get("exit_reason"), p.get("opened_ns"), p.get("closed_ns"), p.get("entry_state")))
        self._maybe_flush()

    def _maybe_flush(self) -> None:
        self.pending += 1
        if self.pending >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        self.con.commit()
        self.pending = 0

    def close(self) -> None:
        self.flush()
        self.con.close()

    # ---- okuma
    def summary(self) -> dict:
        c = self.con
        dec = c.execute("SELECT kind, COUNT(*) FROM decisions GROUP BY kind").fetchall()
        by_kind = {k: n for k, n in dec}
        closed = c.execute("SELECT COUNT(*), COALESCE(SUM(CAST(net_pct AS REAL)),0) FROM positions WHERE state='CLOSED'").fetchone()
        reasons = dict(c.execute("SELECT exit_reason, COUNT(*) FROM positions WHERE exit_reason IS NOT NULL GROUP BY exit_reason").fetchall())
        wins = c.execute("SELECT COUNT(*) FROM positions WHERE state='CLOSED' AND CAST(net_pct AS REAL) > 0").fetchone()[0]
        return {"decisions": sum(by_kind.values()), "approve": by_kind.get("APPROVE", 0), "reject": by_kind.get("REJECT", 0),
                "resize": by_kind.get("RESIZE", 0), "positions_open": c.execute("SELECT COUNT(*) FROM positions WHERE state NOT IN ('CLOSED')").fetchone()[0],
                "positions_closed": closed[0], "net_sum_pct": round(closed[1], 6), "win_rate": (wins / closed[0]) if closed[0] else None,
                "exit_reasons": reasons, "orders": c.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
                "fills": c.execute("SELECT COUNT(*) FROM fills").fetchone()[0]}

    def recent_positions(self, n: int = 20) -> list[dict]:
        cur = self.con.execute("SELECT pos_id,symbol,side,state,qty,entry_price,sl,tp,net_pct,exit_reason,opened_ns,closed_ns,entry_state FROM positions ORDER BY opened_ns DESC LIMIT ?", (n,))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def recent_decisions(self, n: int = 20) -> list[dict]:
        cur = self.con.execute("SELECT t_ms,symbol,kind,reasons,cell,explain FROM decisions ORDER BY id DESC LIMIT ?", (n,))
        cols = [d[0] for d in cur.description]
        return [{**dict(zip(cols, r)), "reasons": json.loads(r[3] or "[]")} for r in cur.fetchall()]
