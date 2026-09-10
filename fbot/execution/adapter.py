"""Execution arayüzü. Live adapter proje sahibi onayına kadar korumalı stub (CLAUDE.md)."""
from __future__ import annotations

from typing import Protocol


class ExecutionAdapter(Protocol):
    def submit(self, command) -> None: ...


class _Recording:
    def __init__(self):
        self.submitted: list = []

    def submit(self, command) -> None:
        self.submitted.append(command)


class PaperExecutionAdapter(_Recording):
    """Simüle execution (Faz 7'de doldurulur)."""


class ReplayExecutionAdapter(_Recording):
    """Replay'de komutları toplar; harness hash'ler."""


class LiveExecutionAdapter:
    """Yarım implementasyon hiç implementasyondan tehlikelidir: her çağrı hata."""

    def submit(self, command) -> None:
        raise RuntimeError("LiveExecutionAdapter korumalı stub: canlı emir yolu proje sahibi onayı olmadan etkinleştirilemez")
