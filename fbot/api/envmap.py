"""Ortam adı → dosya yolu eşlemesi. Saf; beyaz liste dışına çıkmaz.

Konsolun kill switch'i tek bir sabit dosyaya yazıyordu: hangi ortam seçili olursa olsun aynı
dosya güncelleniyordu (F01). Eşleme burada, tek yerde tanımlıdır.
"""
from __future__ import annotations

from pathlib import Path

# docker-compose.yml bağlama noktalarıyla birebir: her ortam kendi data/state alt ağacını görür
_STATE_DIR = {"paper": ("data", "state"), "testnet": ("data", "state", "testnet"), "live": ("data", "state", "live")}


class UnknownEnv(ValueError):
    pass


def known_envs() -> list[str]:
    return sorted(_STATE_DIR)


def state_dir_for(env: str | None, root: Path) -> Path:
    if env not in _STATE_DIR:
        raise UnknownEnv(f"bilinmeyen ortam: {env!r} (geçerli: {', '.join(known_envs())})")
    return Path(root).joinpath(*_STATE_DIR[env])


def kill_path_for(env: str | None, root: Path) -> Path:
    return state_dir_for(env, root) / "kill_switch.json"
