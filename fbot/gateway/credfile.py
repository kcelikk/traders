"""Anahtar dosyasını **çalışırken** okur: konsoldan anahtar değişince servis yeniden başlatılmaz.

Süreç ortam değişkeni yalnızca yedektir; `.env` dosyası tek doğruluk kaynağıdır çünkü konsol
oraya yazar. Gizli anahtar hiçbir zaman log'a, hata metnine veya `repr`'a girmez: dışarıya
yalnızca maskeli anahtar ve içerik parmak izi verilir.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path

from fbot.gateway.signing import Credentials

TESTNET = {"armed": "FBOT_TESTNET_ARMED", "key": "BINANCE_TESTNET_API_KEY", "secret": "BINANCE_TESTNET_API_SECRET"}

# Okuma sırası: sonraki dosya öncekini ezer. `.env` mainnet anahtarını da taşıdığı için testnet
# container'ına bağlanmaz; testnet anahtarı kendi dosyasında durur ve yalnızca o container'a görünür.
def testnet_paths(root: Path | str) -> list[Path]:
    root = Path(root)
    return [root / ".env", root / "data" / "state" / "credentials.env", root / "data" / "state" / "testnet" / "credentials.env"]


class EnvFileUnreadable(OSError):
    """Dosya var ama okunamıyor (çoğunlukla izin). Sessizce yok sayılmaz: servis eski anahtarla
    silahlı kalır ve kullanıcı anahtarı değiştirdiğini sanır."""


def read_env_file(path: Path | str) -> dict:
    """`KEY=value` satırları. Yorum ve boş satır atlanır, tırnaklar soyulur.
    Dosya yoksa boş sözlük; **varsa ama okunamıyorsa** `EnvFileUnreadable`."""
    out: dict[str, str] = {}
    p = Path(path)
    try:
        text = p.read_text()
    except FileNotFoundError:
        return out
    except OSError as e:
        raise EnvFileUnreadable(f"{p}: {e.strerror or e}") from e
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


@dataclass(frozen=True)
class CredState:
    armed: bool
    reason: str
    fingerprint: str
    masked: str
    creds: Credentials | None = field(default=None, repr=False)   # repr'a girmez: sızıntı koruması


def _fingerprint(values: list[str]) -> str:
    h = hashlib.sha256("\x00".join(values).encode()).hexdigest()
    return h[:12]


def read_testnet_state(path, environ: dict | None = None) -> CredState:
    """`path` tek bir dosya ya da dosya listesi olabilir; listede sonraki değer öncekini ezer."""
    paths = [path] if isinstance(path, (str, Path)) else list(path)
    env = dict(environ if environ is not None else os.environ)
    for pth in paths:
        try:
            env.update(read_env_file(pth))
        except EnvFileUnreadable as e:
            # Okunamayan anahtar dosyası = silahsız. Fail-closed: eski anahtarla devam edilmez.
            return CredState(False, f"anahtar dosyası okunamıyor: {e}", "err-" + _fingerprint([str(e)])[:8], "")
    armed_flag, key, sec = (env.get(TESTNET[k], "") or "" for k in ("armed", "key", "secret"))
    fp = _fingerprint([armed_flag, key, sec])
    masked = ("…" + key[-4:]) if len(key) > 4 else ""
    if not armed_flag:
        return CredState(False, "FBOT_TESTNET_ARMED tanımlı değil", fp, masked)
    if not key:
        return CredState(False, "BINANCE_TESTNET_API_KEY tanımlı değil", fp, masked)
    if not sec:
        return CredState(False, "BINANCE_TESTNET_API_SECRET tanımlı değil", fp, masked)
    return CredState(True, f"anahtar {masked}", fp, masked, Credentials(api_key=key, api_secret=sec))
