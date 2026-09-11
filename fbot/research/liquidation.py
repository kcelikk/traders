"""Likidasyon akışı (`forceOrder`) → dakikalık büyüklükler. Saf; I/O yok.

Bu veri arşivde yok, yalnızca kendi kaydımızda var. Fiyattan bağımsız bilgi taşır: kimin zorla
kapatıldığını söyler.

**Semantik:** `S=SELL` bir long pozisyonun zorla kapatılmasıdır (zorunlu satış baskısı),
`S=BUY` bir short pozisyonun kapatılmasıdır (zorunlu alış baskısı). İşaret karıştırılırsa yön
ters döner; testle sabitlendi.

Dolmamış emirler atlanır; miktar olarak dolan miktar (`z`) tercih edilir, yoksa emir miktarı (`q`).
"""
from __future__ import annotations

M = 60_000


def parse_force_order(payload: dict) -> dict | None:
    o = (payload or {}).get("o") or {}
    if o.get("X") != "FILLED":
        return None
    try:
        qty = float(o.get("z") or o["q"])
        price = float(o["ap"] or o["p"])
        sym, side = o["s"], o["S"]
    except (KeyError, TypeError, ValueError):
        return None
    if qty <= 0 or price <= 0 or side not in ("BUY", "SELL"):
        return None
    return {"t_ms": int(payload.get("E") or 0), "symbol": sym,
            "side": "long" if side == "SELL" else "short", "notional": qty * price}


def liq_per_minute(rows) -> dict[tuple[str, int], dict]:
    """(sembol, dakika) → {liq_long_usdt, liq_short_usdt, liq_count}. Olaysız dakika yoktur."""
    out: dict[tuple[str, int], dict] = {}
    for r in rows:
        if not r:
            continue
        k = (r["symbol"], r["t_ms"] // M * M)
        a = out.setdefault(k, {"liq_long_usdt": 0.0, "liq_short_usdt": 0.0, "liq_count": 0})
        a["liq_long_usdt" if r["side"] == "long" else "liq_short_usdt"] += r["notional"]
        a["liq_count"] += 1
    return out
