"""Konsol kimlik doğrulaması: token yoksa yazma uçları kapalı; okuma uçları opsiyonel korumalı."""
import json

import pytest

from fbot.api.auth import AuthConfig, check


def cfg(**kw):
    base = dict(token="s3cret", protect_reads=False, trusted_proxy=True)
    base.update(kw)
    return AuthConfig(**base)


def test_write_requires_token():
    c = cfg()
    assert check("POST", "/api/kill", {}, c) == (False, "token gerekli")
    assert check("POST", "/api/kill", {"authorization": "Bearer s3cret"}, c)[0]
    assert check("POST", "/api/kill", {"x-fbot-token": "s3cret"}, c)[0]
    assert check("POST", "/api/kill", {"x-fbot-token": "yanlis"}, c) == (False, "token geçersiz")


def test_reads_open_unless_protected():
    assert check("GET", "/api/state", {}, cfg())[0]
    assert check("GET", "/", {}, cfg())[0]
    c = cfg(protect_reads=True)
    assert check("GET", "/api/state", {}, c) == (False, "token gerekli")
    assert check("GET", "/api/state", {"x-fbot-token": "s3cret"}, c)[0]


def test_no_token_configured_means_writes_disabled():
    """Token tanımlı değilse yazma uçları tamamen kapalıdır (fail-closed), açık bırakılmaz."""
    c = cfg(token=None)
    ok, why = check("POST", "/api/kill", {"x-fbot-token": "x"}, c)
    assert not ok and "yapılandırılmamış" in why
    assert check("GET", "/api/state", {}, c)[0]


def test_token_compare_is_constant_time():
    import inspect
    from fbot.api import auth
    assert "compare_digest" in inspect.getsource(auth), "token karşılaştırması sabit zamanlı olmalı"


def test_bearer_and_basic_forms():
    c = cfg()
    import base64
    b = base64.b64encode(b"fbot:s3cret").decode()
    assert check("POST", "/api/kill", {"authorization": f"Basic {b}"}, c)[0]
    assert check("POST", "/api/kill", {"authorization": "Basic " + base64.b64encode(b"fbot:yanlis").decode(), }, c)[0] is False
