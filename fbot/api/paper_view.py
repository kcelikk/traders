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


def _meta(con) -> tuple[dict, str | None, dict | None]:
    """Koşunun kaydettiği etkin yapılandırma ve canlılık damgası; eski veritabanlarında yok (F02/F05)."""
    cfg, cfg_hash, hb = {}, None, None
    try:
        rows = dict(con.execute("SELECT key, value FROM meta WHERE key IN ('config','config_hash')").fetchall())
        cfg_hash = rows.get("config_hash")
        cfg = json.loads(rows.get("config") or "{}")
    except (sqlite3.Error, ValueError):
        pass
    try:
        r = con.execute("SELECT ts_ns, detail FROM heartbeat WHERE id=1").fetchone()
        if r:
            hb = {"ts_ns": r[0], "detail": json.loads(r[1] or "{}")}
    except (sqlite3.Error, ValueError):
        pass
    return cfg, cfg_hash, hb


def _rows(con, sql, n=None):
    cur = con.execute(sql, (n,) if n is not None else ())
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


EMPTY = {"run_id": None, "env": None, "runs": [], "positions": [], "open_positions": [], "verdicts": [], "fsm": {},
         "exit_reasons": {}, "metrics": {}, "open_count": 0, "gross_exposure_usdt": 0.0,
         "config": {}, "config_hash": None, "heartbeat": None, "requested_run_id": None, "run_missing": False}

POS_FIELDS = ("pos_id", "symbol", "side", "state", "qty", "entry_price", "sl", "tp", "net_pct", "exit_reason",
              "opened_ns", "closed_ns", "entry_state", "exit_price", "filled_qty")
POS_COLS = ",".join(POS_FIELDS)


def pos_cols(con) -> str:
    """Çalışan bir koşunun veritabanı henüz göç etmemiş olabilir; eksik sütun NULL olarak seçilir."""
    try:
        have = {r[1] for r in con.execute("PRAGMA table_info(positions)")}
    except sqlite3.Error:
        return POS_COLS
    return ",".join(c if c in have else f"NULL AS {c}" for c in POS_FIELDS)


def _notional(p: dict) -> float | None:
    """Maruziyet gerçek miktardan hesaplanır; sabit 80 USDT varsaymak yanlış sayı üretir (F07)."""
    try:
        q = p.get("filled_qty") or p.get("qty")
        if q is None or p.get("entry_price") is None:
            return None
        q = float(q)
        if q <= 0:
            return None          # kapanan pozisyonun miktarı sıfırlanır: "bilinmiyor", "sıfır maruziyet" değil
        return round(q * float(p["entry_price"]), 2)
    except (TypeError, ValueError):
        return None


def paper_snapshot(recordings: Path, run_id: str | None = None) -> dict:
    runs = find_paper_runs(recordings)
    missing = False
    if run_id:
        want = [r for r in runs if r["run_id"] == run_id]
        missing = not want
        runs = want or runs
    if not runs:
        return {**EMPTY, "requested_run_id": run_id, "run_missing": bool(run_id)}
    run = runs[0]
    con = sqlite3.connect(f"file:{run['db']}?mode=ro", uri=True)
    try:
        # Açık pozisyonlar ayrı sorgulanır: son 50 kaydın dışında kalıp ekrandan düşmemeleri gerekir (F06)
        cols = pos_cols(con)
        open_pos = _rows(con, f"SELECT {cols} FROM positions WHERE state != 'CLOSED' ORDER BY opened_ns DESC")
        pos = _rows(con, f"SELECT {cols} FROM positions ORDER BY opened_ns DESC LIMIT ?", 50)
        dec = _rows(con, "SELECT t_ms,symbol,kind,reasons,cell,explain FROM decisions ORDER BY id DESC LIMIT ?", 25)
        fsm = dict(con.execute("SELECT state, COUNT(*) FROM positions GROUP BY state").fetchall())
        reasons = dict(con.execute("SELECT exit_reason, COUNT(*) FROM positions WHERE exit_reason IS NOT NULL GROUP BY exit_reason").fetchall())
        cfg, cfg_hash, hb = _meta(con)
    finally:
        con.close()
    for p in pos + open_pos:
        p["net_pct"] = float(p["net_pct"]) if p["net_pct"] is not None else None
        p["notional_usdt"] = _notional(p)
        # Kapanmış pozisyonun referans fiyatı çıkış fiyatıdır, güncel mark değil
        p["ref_price"] = p["exit_price"] if p["state"] == "CLOSED" else None
    for d in dec:
        d["reasons"] = json.loads(d["reasons"] or "[]")
    return {"run_id": run["run_id"], "env": run["env"], "runs": [{"run_id": r["run_id"], "env": r["env"]} for r in runs[:8]],
            "positions": pos, "open_positions": open_pos, "verdicts": dec,
            "fsm": fsm, "exit_reasons": reasons, "metrics": metrics(Path(run["db"])),
            "open_count": len(open_pos),
            "gross_exposure_usdt": round(sum(p["notional_usdt"] or 0 for p in open_pos), 2),
            "config": cfg, "config_hash": cfg_hash, "heartbeat": hb,
            "requested_run_id": run_id, "run_missing": missing}
