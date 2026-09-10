"""Konsol için paper görünümü: koşu dizinlerini bulur, SQLite'tan pozisyon/karar/metrik okur. Salt okunur."""
from __future__ import annotations

import json
import sqlite3
from collections import Counter
from pathlib import Path

from scripts.paper_summary import metrics


def _env_of(run_id: str, db=None) -> str:
    """Ortam veritabanındaki `meta.env` alanından; yoksa run_id önekinden (eski koşular)."""
    if db is not None:
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
            row = con.execute("SELECT value FROM meta WHERE key='env'").fetchone()
            con.close()
            if row:
                return row[0]
        except sqlite3.Error:
            pass
    return "testnet" if run_id.startswith("testnet") else ("live" if run_id.startswith("live") else "paper")


def find_paper_runs(recordings: Path) -> list[dict]:
    out = []
    for d in Path(recordings).glob("*/paper.db"):
        out.append({"run_id": d.parent.name, "db": str(d), "mtime": d.stat().st_mtime, "env": _env_of(d.parent.name, d)})
    return sorted(out, key=lambda r: r["mtime"], reverse=True)


def environments(recordings: Path) -> list[dict]:
    """Her koşu için ortam, açık pozisyon ve özet — konsolun ortam seçimi için."""
    out = []
    for r in find_paper_runs(recordings):
        try:
            con = sqlite3.connect(f"file:{r['db']}?mode=ro", uri=True)
            fsm = dict(con.execute("SELECT state, COUNT(*) FROM positions GROUP BY state").fetchall())
            con.close()
            m = metrics(Path(r["db"]))
        except sqlite3.Error:
            fsm, m = {}, {}
        out.append({"run_id": r["run_id"], "env": r["env"], "mtime": r["mtime"],
                    "positions": sum(fsm.values()), "open": sum(n for s, n in fsm.items() if s != "CLOSED"),
                    "metrics": m})
    return out


def _rows(con, sql, n=None):
    cur = con.execute(sql, (n,) if n is not None else ())
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def paper_snapshot(recordings: Path, run_id: str | None = None) -> dict:
    runs = find_paper_runs(recordings)
    if run_id:
        runs = [r for r in runs if r["run_id"] == run_id] or runs
    if not runs:
        return {"run_id": None, "env": None, "runs": [], "positions": [], "verdicts": [], "fsm": {}, "exit_reasons": {}, "metrics": {}, "open_count": 0}
    run = runs[0]
    con = sqlite3.connect(f"file:{run['db']}?mode=ro", uri=True)
    try:
        pos = _rows(con, "SELECT pos_id,symbol,side,state,qty,entry_price,sl,tp,net_pct,exit_reason,opened_ns,closed_ns,entry_state "
                         "FROM positions ORDER BY opened_ns DESC LIMIT ?", 50)
        dec = _rows(con, "SELECT t_ms,symbol,kind,reasons,cell,explain FROM decisions ORDER BY id DESC LIMIT ?", 25)
        fsm = dict(con.execute("SELECT state, COUNT(*) FROM positions GROUP BY state").fetchall())
        reasons = dict(con.execute("SELECT exit_reason, COUNT(*) FROM positions WHERE exit_reason IS NOT NULL GROUP BY exit_reason").fetchall())
    finally:
        con.close()
    for p in pos:
        p["net_pct"] = float(p["net_pct"]) if p["net_pct"] is not None else None
    for d in dec:
        d["reasons"] = json.loads(d["reasons"] or "[]")
    return {"run_id": run["run_id"], "env": run["env"], "runs": [{"run_id": r["run_id"], "env": r["env"]} for r in runs[:8]],
            "positions": pos, "verdicts": dec,
            "fsm": fsm, "exit_reasons": reasons, "metrics": metrics(Path(run["db"])),
            "open_count": sum(n for s, n in fsm.items() if s != "CLOSED")}
