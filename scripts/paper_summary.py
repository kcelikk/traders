"""Paper koşusunun SQLite özeti (BÖLÜM 12 metrik seti). Kullanım: python -m scripts.paper_summary <paper.db> [--json]

Kârlılık gösterilmedi (ADR 0010). Dolum modeli sınırı: kuyruk pozisyonu modellenmez → maker dolum oranı iyimser (ADR 0013)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path


def metrics(db: Path) -> dict:
    con = sqlite3.connect(str(db))
    # Drawdown zaman dizisidir: kapanış sırası olmadan hesaplanırsa anlamsız bir sayı çıkar (F08)
    closed = con.execute("SELECT net_pct, exit_reason, opened_ns, closed_ns, symbol, side FROM positions "
                         "WHERE state='CLOSED' AND net_pct IS NOT NULL ORDER BY COALESCE(closed_ns, opened_ns), pos_id").fetchall()
    nets = [float(r[0]) for r in closed]
    wins = [x for x in nets if x > 0]
    losses = [x for x in nets if x <= 0]
    eq, peak, dd = 0.0, 0.0, 0.0
    for x in nets:
        eq += x
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    holds = [(r[3] - r[2]) / 6e10 for r in closed if r[2] and r[3]]
    dec = dict(con.execute("SELECT kind, COUNT(*) FROM decisions GROUP BY kind").fetchall())
    reasons = dict(con.execute("SELECT exit_reason, COUNT(*) FROM positions WHERE exit_reason IS NOT NULL GROUP BY exit_reason").fetchall())
    rej = {}
    for (r,) in con.execute("SELECT reasons FROM decisions WHERE kind='REJECT'"):
        for x in json.loads(r or "[]"):
            rej[x] = rej.get(x, 0) + 1
    return {
        "işlem": len(nets), "net_toplam_pct": round(sum(nets), 4), "net_ortalama_pct": round(sum(nets) / len(nets), 4) if nets else None,
        "kazanma_oranı": round(len(wins) / len(nets), 4) if nets else None,
        "ortalama_kazanç_pct": round(sum(wins) / len(wins), 4) if wins else None,
        "ortalama_kayıp_pct": round(sum(losses) / len(losses), 4) if losses else None,
        "profit_factor": round(sum(wins) / abs(sum(losses)), 3) if losses and sum(losses) else None,
        "beklenti_pct": round(sum(nets) / len(nets), 4) if nets else None,
        "maks_drawdown_pct": round(dd, 4), "risk_ayarlı": round(sum(nets) / dd, 3) if dd else None,
        "ortalama_tutma_dk": round(sum(holds) / len(holds), 1) if holds else None,
        "çıkış_nedenleri": reasons, "kararlar": dec, "ret_nedenleri": rej,
        "emir": con.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "dolum": con.execute("SELECT COUNT(*) FROM fills").fetchone()[0],
        "açık_pozisyon": con.execute("SELECT COUNT(*) FROM positions WHERE state NOT IN ('CLOSED')").fetchone()[0],
        "not": "kârlılık gösterilmedi (ADR 0010); maker dolum oranı iyimser, kuyruk pozisyonu modellenmez (ADR 0013)",
    }


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    m = metrics(Path(a.db))
    if a.json:
        print(json.dumps(m, ensure_ascii=False))
    else:
        for k, v in m.items():
            print(f"{k:22s} {v}")


if __name__ == "__main__":
    main(sys.argv[1:])
