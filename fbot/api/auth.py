"""Konsol kimlik doğrulaması. Fail-closed: token yapılandırılmamışsa yazma uçları kapalıdır.

Konsol ters vekil (nginx) arkasında çalışır; nginx ayrıca HTTP Basic Auth uygular. Bu katman
ikinci savunmadır: vekil yanlış yapılandırılsa bile kill switch uçları token olmadan çalışmaz.
"""
from __future__ import annotations

import base64
import hmac
from dataclasses import dataclass

WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


@dataclass(frozen=True)
class AuthConfig:
    token: str | None
    protect_reads: bool = False
    trusted_proxy: bool = True


def _presented(headers: dict) -> list[str]:
    h = {k.lower(): v for k, v in headers.items()}
    out = []
    t = h.get("x-fbot-token")
    if t:
        out.append(t)
    a = h.get("authorization", "")
    if a.startswith("Bearer "):
        out.append(a[7:])
    elif a.startswith("Basic "):
        try:
            out.append(base64.b64decode(a[6:]).decode().split(":", 1)[1])
        except Exception:  # noqa: BLE001
            pass
    return out


def check(method: str, path: str, headers: dict, cfg: AuthConfig) -> tuple[bool, str]:
    needs = method.upper() in WRITE_METHODS or (cfg.protect_reads and path.startswith("/api/"))
    if not needs:
        return True, ""
    if not cfg.token:
        return False, "yazma uçları yapılandırılmamış (FBOT_UI_TOKEN yok)"
    given = _presented(headers)
    if not given:
        return False, "token gerekli"
    for g in given:
        if hmac.compare_digest(g, cfg.token):
            return True, ""
    return False, "token geçersiz"
