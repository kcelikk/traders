"""REST imzalama — HMAC SHA256, yalnızca stdlib (ADR 0015).

Doğrulanmış kural (docs/binance-api-verification.md §7): `totalParams` = query string + request body,
HMAC anahtarı `secretKey`. Parametre sırası korunur (WS API'nin alfabetik sıralama kuralı REST'te geçerli değil).

Güvenlik: anahtar ve gizli anahtar yalnızca ortam değişkeninden gelir, asla loglanmaz, `repr` maskelidir.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import urllib.parse
from dataclasses import dataclass


@dataclass(frozen=True)
class Credentials:
    api_key: str
    api_secret: str

    def __post_init__(self):
        if not self.api_key or not self.api_secret:
            raise ValueError("API anahtarı ve gizli anahtar boş olamaz (.env üzerinden verilir)")

    @property
    def masked_key(self) -> str:
        k = self.api_key
        return ("…" + k[-4:]) if len(k) > 4 else "…"

    def __repr__(self) -> str:
        return f"Credentials(key={self.masked_key}, secret=***)"

    __str__ = __repr__


def sign_query(params: dict, creds: Credentials) -> tuple[str, str]:
    """(query_string, signature). `signature` çağıran tarafından sona eklenir."""
    clean = {k: v for k, v in params.items() if v is not None}
    q = urllib.parse.urlencode(clean)
    sig = hmac.new(creds.api_secret.encode(), q.encode(), hashlib.sha256).hexdigest()
    return q, sig


def load_testnet_credentials() -> Credentials:
    """Testnet anahtarları. `FBOT_TESTNET_ARMED` olmadan yüklenmez (CLAUDE.md onay kapısı)."""
    if not os.environ.get("FBOT_TESTNET_ARMED"):
        raise RuntimeError("FBOT_TESTNET_ARMED tanımlı değil: testnet emir yolu bilinçli olarak etkinleştirilmelidir")
    key = os.environ.get("BINANCE_TESTNET_API_KEY")
    sec = os.environ.get("BINANCE_TESTNET_API_SECRET")
    if not key or not sec:
        raise RuntimeError("BINANCE_TESTNET_API_KEY / BINANCE_TESTNET_API_SECRET tanımlı değil (.env)")
    return Credentials(api_key=key, api_secret=sec)
