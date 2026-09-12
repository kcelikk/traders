"""`clientOrderId` / `clientAlgoId` grameri — tek doğruluk kaynağı. Saf, deterministik.

Binance sınırı 36 karakter (**36 dahil kabul ediliyor**, Gate 0 testnet doğrulaması §3; hata metni
"less than 36" dese de). Eski gramer `e{sembol}{bar_end_ms}{L|S}` 36'ya kırpılıyordu; kırpılmış
`pos_id`'ye `-SL-v1` eklenince 42 karaktere çıkıyor ve koruma emri `-4015` ile reddediliyordu.

Yeni gramer uzunluğu **girdiden bağımsız** sabitler:

    pos_id  = {tag}{L|S}{10 hex}          örn. "f1La3c9d21e4f"   (≤ 4 + 1 + 10 = 15)
    algo    = {pos_id}-{SL|TP}-v{n}       (≤ 15 + 8 = 23)
    çıkış   = {pos_id}-{X|TP1}-v{n}

Ayraç korunur: simülatör ve trader, exec olayında `pos_id`'yi önekten çözüyor (`pos_id_of`).
Gate 3'te sahipsiz emir temizliği de "bizim gramerimize uyanlar" ayrımını buradan yapacak.
"""
from __future__ import annotations

import hashlib

MAX_LEN = 36
SEP = "-"
HASH_LEN = 10
MAX_TAG = 4


def _h(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:HASH_LEN]


def check(cid: str) -> str:
    if len(cid) > MAX_LEN:
        raise ValueError(f"clientOrderId {len(cid)} karakter, sınır {MAX_LEN}: {cid!r}")
    return cid


def entry_cid(tag: str, symbol: str, bar_end_ms: int, side: str) -> str:
    """Giriş emrinin kimliği; aynı zamanda `pos_id`. Aynı (sembol, bar, yön) → aynı kimlik."""
    if not tag or len(tag) > MAX_TAG or SEP in tag:
        raise ValueError(f"strategy_tag 1-{MAX_TAG} karakter ve '{SEP}' içermemeli: {tag!r}")
    return check(f"{tag}{'L' if side == 'long' else 'S'}{_h(symbol, bar_end_ms, side)}")


def algo_cid(pos_id: str, role: str, version: int) -> str:
    return check(f"{pos_id}{SEP}{role}{SEP}v{version}")


def exit_cid(pos_id: str, tag: str, seq: int) -> str:
    return check(f"{pos_id}{SEP}{tag}{SEP}v{seq}")


def pos_id_of(cid: str) -> str:
    """Emir kimliğinden pozisyon kimliği. Giriş kimliğinde ayraç yoktur, kendisini döndürür."""
    return cid.split(SEP, 1)[0]
