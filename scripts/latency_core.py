"""Faz 0 gecikme ölçümü — saf çekirdek.

Bu modülde I/O, ağ, saat okuma yoktur. Tüm girdiler parametre olarak gelir.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable


def percentiles(values: Iterable[float], ps=(50, 95, 99)) -> dict:
    """Nearest-rank persentil. Boş girdi → None. Girdi değiştirilmez."""
    vals = sorted(v for v in values if v is not None)
    out = {}
    n = len(vals)
    for p in ps:
        key = f"p{p}"
        if n == 0:
            out[key] = None
        else:
            rank = max(1, math.ceil(p / 100 * n))
            out[key] = vals[rank - 1]
    return out


def rest_sample(send_wall_ms: int, recv_wall_ms: int, server_time_ms: int | None) -> dict:
    """Tek REST örneği. skew = server - (send+recv)/2 (orta nokta tahmini)."""
    rtt = recv_wall_ms - send_wall_ms
    skew = None
    if server_time_ms is not None:
        skew = server_time_ms - (send_wall_ms + recv_wall_ms) / 2
    return {"wall_ms": send_wall_ms, "rtt_ms": rtt, "skew_ms": skew}


def ws_lag(msg: dict, recv_wall_ms: int) -> dict | None:
    """Market stream mesajından E/T gecikmesi. Kontrol mesajlarında None."""
    if "data" in msg and isinstance(msg["data"], dict):
        stream = msg.get("stream")
        data = msg["data"]
    else:
        data = msg
        stream = None
    if "E" not in data or "e" not in data:
        return None
    if stream is None:
        stream = f"{data.get('s', '?')}@{data['e']}"
    e_time = data["E"]
    # markPriceUpdate'te T bir sonraki funding zamanıdır, event zamanı değil.
    t_time = data.get("T") if data["e"] != "markPriceUpdate" else None
    return {
        "wall_ms": recv_wall_ms,
        "stream": stream,
        "E": e_time,
        "T": t_time,
        "lag_E_ms": recv_wall_ms - e_time,
        "lag_T_ms": (recv_wall_ms - t_time) if t_time is not None else None,
    }


def summarize(rows: Iterable[dict], key: str) -> dict:
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return {"count": 0, "min": None, "max": None, "mean": None, "p50": None, "p95": None, "p99": None}
    return {
        "count": len(vals),
        "min": min(vals),
        "max": max(vals),
        "mean": sum(vals) / len(vals),
        **percentiles(vals),
    }


def hour_bucket(wall_ms: int) -> str:
    """UTC saat kovası: 'YYYY-MM-DDTHH'."""
    return datetime.fromtimestamp(wall_ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H")
