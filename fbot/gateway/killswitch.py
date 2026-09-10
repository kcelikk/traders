"""Kalıcı kill switch (I/O kenarı). Restart'ı hayatta kalır; yalnızca elle sıfırlanır. Çekirdek yalnızca `active` bayrağını okur."""
from __future__ import annotations

import json
from pathlib import Path


class KillSwitch:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.hist_path = self.path.with_suffix(".history.jsonl")
        self.state = {"active": False}
        if self.path.exists():
            self.state = json.loads(self.path.read_text())

    @property
    def active(self) -> bool:
        return bool(self.state.get("active"))

    def _write(self, event: dict):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state))
        tmp.replace(self.path)          # atomik
        with self.hist_path.open("a") as f:
            f.write(json.dumps(event) + "\n")

    def trigger(self, reason: str, now_ns: int, git_sha: str) -> None:
        if self.active:
            return                       # ilk neden korunur
        self.state = {"active": True, "reason": reason, "ts_ns": now_ns, "git_sha": git_sha}
        self._write({"event": "trigger", **self.state})

    def reset(self, note: str, now_ns: int) -> None:
        self.state = {"active": False, "reset_note": note, "reset_ts_ns": now_ns}
        self._write({"event": "reset", "note": note, "ts_ns": now_ns})

    def history(self) -> list[dict]:
        if not self.hist_path.exists():
            return []
        return [json.loads(l) for l in self.hist_path.read_text().splitlines() if l.strip()]
