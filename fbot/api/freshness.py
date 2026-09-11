"""Veri tazeliği değerlendirmesi. Saf fonksiyon; saat parametre olarak gelir.

Konsol geçmiş kaydı oynatırken ekranda 18 saat önceki fiyatlar duruyordu ve bunu belli eden
bir işaret yoktu (F05). Bu modül durumu tek bir nesnede toplar; arayüz onu açıkça gösterir.
"""
from __future__ import annotations

NS = 1_000_000_000
DEFAULT_THRESHOLD_S = 30


def assess(loading: bool, tail_lines: int, last_event_ns: int | None, now_ns: int,
           stale_age_s: dict, thresholds_s: dict, default_threshold_s: int = DEFAULT_THRESHOLD_S) -> dict:
    age = None if last_event_ns is None else max(0.0, (now_ns - last_event_ns) / NS)
    stale_cats = sorted(c for c, a in (stale_age_s or {}).items()
                        if a is not None and a > (thresholds_s or {}).get(c, default_threshold_s))
    if loading:
        status, reason = "loading", "geçmiş kayıt oynatılıyor · ekrandaki değerler canlı değil"
    elif tail_lines <= 0 and last_event_ns is None:
        status, reason = "no_data", "kayıt akışından hiç olay okunmadı"
    elif stale_cats or (age is not None and age > default_threshold_s):
        status = "stale"
        reason = ("bayat kategori: " + ", ".join(stale_cats)) if stale_cats else f"son olay {age:.0f} s önce"
    else:
        status, reason = "live", "akış canlı"
    return {"status": status, "live": status == "live", "loading": bool(loading), "tail_lines": tail_lines,
            "last_event_ns": last_event_ns, "data_age_s": None if age is None else round(age, 1),
            "stale_categories": stale_cats, "stale_age_s": dict(stale_age_s or {}),
            "thresholds_s": dict(thresholds_s or {}), "reason": reason}
