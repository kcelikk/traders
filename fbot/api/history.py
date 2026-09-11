"""İşlem geçmişi ve performans dökümü (konsol "Geçmiş" ekranı). Salt okunur SQLite.

Kârlılık gösterilmedi (ADR 0010): buradaki sayılar geçmiş koşunun ölçümüdür, gelecek beklentisi değildir.
Net yüzdeler maliyet düşülmüş değerlerdir (PositionManager.net_unrealized_pct).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from fbot.api.paper_view import _notional, _rows, find_paper_runs, pos_cols

EMPTY_PERF = {"by_symbol": {}, "by_exit_reason": {}, "by_entry_state": {}, "by_side": {}, "equity": []}


def _bucket(rows, key: str) -> dict:
    out: dict[str, dict] = {}
    for r in rows:
        k = r.get(key) or "—"
        b = out.setdefault(k, {"n": 0, "wins": 0, "net_pct": 0.0, "net_usdt": 0.0, "usdt_n": 0})
        b["n"] += 1
        net = r.get("net_pct") or 0.0
        b["wins"] += 1 if net > 0 else 0
        b["net_pct"] += net
        if r.get("net_usdt") is not None:
            b["usdt_n"] += 1
            b["net_usdt"] += r["net_usdt"]
    for b in out.values():
        b["net_pct"] = round(b["net_pct"], 4)
        # Miktarı bilinmeyen işlemler için USDT toplamı yok; 0 yazmak yanlış bilgi olur
        b["net_usdt"] = round(b["net_usdt"], 4) if b.pop("usdt_n") else None
        b["win_rate"] = round(b["wins"] / b["n"], 4) if b["n"] else None
        b["avg_net_pct"] = round(b["net_pct"] / b["n"], 4) if b["n"] else None
    return out


def history(recordings: Path, run_id: str | None = None, limit: int = 100, offset: int = 0) -> dict:
    runs = find_paper_runs(recordings)
    if run_id:
        runs = [r for r in runs if r["run_id"] == run_id]
    if not runs:
        return {"run_id": None, "env": None, "run_missing": True, "trades": [], "total": 0,
                "limit": limit, "offset": offset, "performance": EMPTY_PERF}
    run = runs[0]
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    con = sqlite3.connect(f"file:{run['db']}?mode=ro", uri=True)
    try:
        total = con.execute("SELECT COUNT(*) FROM positions WHERE state='CLOSED'").fetchone()[0]
        cols = pos_cols(con)
        page = _rows(con, f"SELECT {cols} FROM positions WHERE state='CLOSED' "
                          f"ORDER BY COALESCE(closed_ns, opened_ns) DESC, pos_id DESC LIMIT {limit} OFFSET {offset}")
        allr = _rows(con, f"SELECT {cols} FROM positions WHERE state='CLOSED' "
                          "ORDER BY COALESCE(closed_ns, opened_ns), pos_id")
    finally:
        con.close()
    for r in page + allr:
        r["net_pct"] = float(r["net_pct"]) if r["net_pct"] is not None else None
        r["notional_usdt"] = _notional(r)
        r["net_usdt"] = (round(r["net_pct"] / 100 * r["notional_usdt"], 4)
                         if r["net_pct"] is not None and r["notional_usdt"] else None)
        r["hold_ms"] = ((r["closed_ns"] - r["opened_ns"]) // 1_000_000
                        if r["closed_ns"] and r["opened_ns"] is not None else None)
    eq, cum = [], 0.0
    for r in allr:
        cum += r["net_pct"] or 0.0
        eq.append({"t_ms": (r["closed_ns"] or 0) // 1_000_000, "cum_net_pct": round(cum, 4), "pos_id": r["pos_id"]})
    perf = {"by_symbol": _bucket(allr, "symbol"), "by_exit_reason": _bucket(allr, "exit_reason"),
            "by_entry_state": _bucket(allr, "entry_state"), "by_side": _bucket(allr, "side"), "equity": eq[-500:]}
    return {"run_id": run["run_id"], "env": run["env"], "run_missing": False, "trades": page, "total": total,
            "limit": limit, "offset": offset, "performance": perf,
            "note": "kârlılık gösterilmedi (ADR 0010); maker dolum oranı iyimser (ADR 0013)"}
