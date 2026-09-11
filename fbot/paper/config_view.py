"""Etkin yapılandırmanın JSON'a uygun görünümü. Saf; I/O yok.

Konsol, koşunun *gerçekte* kullandığı eşikleri gösterir. Sabit varsayılan göstermek yanlış bilgi üretir (F02).
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from decimal import Decimal
from enum import Enum


def effective_config(obj):
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: effective_config(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {str(k): effective_config(v) for k, v in obj.items()}
    if isinstance(obj, (set, frozenset)):
        return sorted(effective_config(v) for v in obj)
    if isinstance(obj, (list, tuple)):
        return [effective_config(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)
