"""Koşu kimliği: her kayıt satırının hangi koşuya, moda, stratejiye ve koda ait olduğu.

Neden `fbot/core/` altında değil: dosya okur (`code_hash`), yani saf değildir.

İki ayrı config hash'i tutulur:
  · `config_hash` — TOML dosyasının **ham baytları** (`fbot/config.py`). Yorum değişince de değişir.
  · `config_semantic_hash` — `effective_config` çıktısının kanonik JSON'u. Yalnız **etkin değer**
    değişince değişir; ortam değişkeni override'larını da kapsar.

`code_hash` gerekli çünkü container'da `git_sha` "unknown" dönebiliyor
(`fbot/recorder/main.py:git_sha`), o zaman kodun hangi sürüm olduğunu söyleyecek başka bir şey kalmıyor.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

MODES = ("replay", "paper", "testnet", "live")

# Her satır bazlı tabloya eklenen kimlik sütunları; `RunIdentity.row()` bu sırayla döner.
ROW_COLS = ("mode", "strategy_id", "strategy_version", "code_hash", "reactor_id")


def code_hash(pkg_dir: Path | str) -> str:
    """Paketin tüm `.py` dosyalarının içeriğinden türetilen 12 hex'lik parmak izi."""
    root = Path(pkg_dir)
    if not root.is_dir():
        raise FileNotFoundError(f"kod dizini yok: {root}")
    h = hashlib.sha256()
    for f in sorted(root.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        h.update(str(f.relative_to(root)).encode())
        h.update(b"\0")
        h.update(f.read_bytes())
        h.update(b"\0")
    return h.hexdigest()[:12]


def semantic_hash(effective: dict) -> str:
    """Etkin yapılandırmanın kanonik JSON sha256'sı. Anahtar sırasından bağımsızdır."""
    return hashlib.sha256(json.dumps(effective, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:12]


@dataclass(frozen=True)
class RunIdentity:
    run_id: str
    mode: str
    strategy_id: str | None
    strategy_version: str | None
    config_hash: str
    config_semantic_hash: str
    code_hash: str
    git_sha: str
    restart_no: int
    reactor_id: str | None = None    # Gate 4'te doldurulur; sütun bugün açılır ki şemaya iki kez dokunulmasın

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"bilinmeyen mod: {self.mode!r} (geçerli: {', '.join(MODES)})")

    def as_dict(self) -> dict:
        return {"run_id": self.run_id, "mode": self.mode, "strategy_id": self.strategy_id,
                "strategy_version": self.strategy_version, "config_hash": self.config_hash,
                "config_semantic_hash": self.config_semantic_hash, "code_hash": self.code_hash,
                "reactor_id": self.reactor_id, "git_sha": self.git_sha, "restart_no": self.restart_no}

    def row(self) -> tuple:
        """Satır bazlı tablolara eklenen alt küme, `ROW_COLS` sırasıyla (her satırda tekrarlanır)."""
        return (self.mode, self.strategy_id, self.strategy_version, self.code_hash, self.reactor_id)
