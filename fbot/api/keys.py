"""API anahtarı yönetimi (konsol). **Yalnızca yazma**: hiçbir uç gizli anahtarı geri döndürmez.

Güvenlik kuralları (CLAUDE.md):
  · Anahtar yalnızca `.env` içinde durur, izin 600, atomik yazım, diğer satırlar korunur.
  · Yanıtlarda yalnızca maskeli anahtar ve "tanımlı mı" bilgisi bulunur; gizli anahtar asla dönmez.
  · Değerler tek satır olmak zorunda (enjeksiyon koruması).
  · Mainnet anahtarı için ek kapı: `FBOT_LIVE_KEYS_ALLOWED` sunucuda tanımlı olmalı.
"""
from __future__ import annotations

import os
from pathlib import Path

VARS = {
    "testnet": {"key": "BINANCE_TESTNET_API_KEY", "secret": "BINANCE_TESTNET_API_SECRET", "armed": "FBOT_TESTNET_ARMED"},
    "live": {"key": "BINANCE_API_KEY", "secret": "BINANCE_API_SECRET", "armed": "FBOT_LIVE_ARMED"},
}


class KeyError_(ValueError):
    pass


def _read(path: Path) -> dict:
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                out[k.strip()] = v
    return out


def _mask(v: str) -> str:
    return ("…" + v[-4:]) if v and len(v) > 4 else ("…" if v else "")


def key_status(path: Path) -> dict:
    env = _read(path)
    out = {}
    for name, keys in VARS.items():
        k, s, a = env.get(keys["key"], ""), env.get(keys["secret"], ""), env.get(keys["armed"], "")
        out[name] = {"key_set": bool(k), "secret_set": bool(s), "armed": bool(a), "masked": _mask(k), "armed_value": a[:32]}
    out["live"]["gate_open"] = bool(os.environ.get("FBOT_LIVE_KEYS_ALLOWED"))
    return out


def write_keys(path: Path, env_name: str, values: dict, require_gate: bool = False) -> dict:
    if env_name not in VARS:
        raise KeyError_(f"bilinmeyen ortam: {env_name}")
    if env_name == "live" and require_gate and not os.environ.get("FBOT_LIVE_KEYS_ALLOWED"):
        raise KeyError_("mainnet anahtarı yazılamaz: sunucuda FBOT_LIVE_KEYS_ALLOWED tanımlı değil")
    for field, v in values.items():
        if field not in ("key", "secret", "armed"):
            raise KeyError_(f"bilinmeyen alan: {field}")
        if v is None:
            continue
        if "\n" in str(v) or "\r" in str(v):
            raise KeyError_("değerde satır sonu olamaz")
        if field in ("key", "secret") and v and len(str(v)) < 16:
            raise KeyError_(f"{field} çok kısa (en az 16 karakter)")
    path = Path(path)
    env_lines = path.read_text().splitlines() if path.exists() else []
    updates = {VARS[env_name][f]: str(values[f]) for f in values if values[f] is not None}
    seen, out = set(), []
    for line in env_lines:
        k = line.split("=", 1)[0].strip() if "=" in line else None
        if k in updates:
            out.append(f"{k}={updates[k]}")
            seen.add(k)
        else:
            out.append(line)
    for k, v in updates.items():
        if k not in seen:
            out.append(f"{k}={v}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)
    return {"env": env_name, "updated": sorted(updates), "note": "servisin görmesi için yeniden başlatılması gerekir"}
