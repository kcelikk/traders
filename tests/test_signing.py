"""REST imzalama (Faz 9, testnet): HMAC SHA256, stdlib. Doğrulanmış kural: totalParams = query string + body."""
import hashlib
import hmac as _hmac

import pytest

from fbot.gateway.signing import Credentials, sign_query


def test_signature_matches_reference_hmac():
    c = Credentials(api_key="KEY", api_secret="SECRET")
    q, sig = sign_query({"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.001", "timestamp": 1700000000000}, c)
    expected = _hmac.new(b"SECRET", q.encode(), hashlib.sha256).hexdigest()
    assert sig == expected
    assert q.startswith("symbol=BTCUSDT&side=BUY") and "signature" not in q


def test_param_order_is_preserved_not_sorted():
    """REST imzasında sıra korunur (WS API'de alfabetik; ikisi farklı kural)."""
    c = Credentials(api_key="K", api_secret="S")
    q1, _ = sign_query({"b": 1, "a": 2}, c)
    q2, _ = sign_query({"a": 2, "b": 1}, c)
    assert q1 == "b=1&a=2" and q2 == "a=2&b=1"


def test_none_values_are_dropped():
    c = Credentials(api_key="K", api_secret="S")
    q, _ = sign_query({"symbol": "X", "price": None, "qty": "1"}, c)
    assert q == "symbol=X&qty=1"


def test_credentials_never_expose_secret():
    c = Credentials(api_key="ABCDEFGH12345678", api_secret="TOPSECRET")
    assert "TOPSECRET" not in repr(c) and "TOPSECRET" not in str(c)
    assert "ABCDEFGH" not in repr(c)          # anahtar da maskeli
    assert c.masked_key.endswith("5678") and len(c.masked_key) <= 12


def test_missing_credentials_raise():
    with pytest.raises(ValueError, match="anahtar"):
        Credentials(api_key="", api_secret="x")
    with pytest.raises(ValueError, match="anahtar"):
        Credentials(api_key="x", api_secret="")


def test_load_from_env_requires_testnet_arm(monkeypatch):
    from fbot.gateway.signing import load_testnet_credentials
    monkeypatch.delenv("FBOT_TESTNET_ARMED", raising=False)
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "k")
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "s")
    with pytest.raises(RuntimeError, match="FBOT_TESTNET_ARMED"):
        load_testnet_credentials()
    monkeypatch.setenv("FBOT_TESTNET_ARMED", "2026-09-10")
    c = load_testnet_credentials()
    assert c.masked_key and c.api_secret == "s"


def test_load_from_env_missing_key_is_clear(monkeypatch):
    from fbot.gateway.signing import load_testnet_credentials
    monkeypatch.setenv("FBOT_TESTNET_ARMED", "1")
    monkeypatch.delenv("BINANCE_TESTNET_API_KEY", raising=False)
    monkeypatch.delenv("BINANCE_TESTNET_API_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="BINANCE_TESTNET_API_KEY"):
        load_testnet_credentials()
