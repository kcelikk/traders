"""Hata enjeksiyon altyapısının kendisi test edilir.

Bu altyapı Gate 1–5'teki riskli refactor'ların güvenlik ağı; çalıştığı kanıtlanmadan
üzerine test yazılmaz. Repoda bugüne kadar timeout ve bağlantı kopması hiç enjekte edilemiyordu.
"""
import socket
import time

import pytest

from fbot.gateway.signing import Credentials
from fbot.gateway.testnet import TestnetClient, TestnetError
from tests.fake import FakeHTTP, delay, drop_connection, malformed, timeout
from tests.fake.http import err, ok

CREDS = Credentials(api_key="KEY1234567890", api_secret="SECRET")


def client(responses):
    return TestnetClient(CREDS, http=FakeHTTP(responses))


def test_timeout_propagates_as_an_exception_not_a_response():
    """Bugün `TestnetClient` timeout'u yakalamıyor; bu test mevcut davranışı sabitler.
    Gate 2 bunu `unknown_execution=True` ile UNKNOWN'a çevirecek ve test o zaman güncellenecek."""
    c = client([timeout()])
    with pytest.raises(socket.timeout):
        c.signed("POST", "/fapi/v1/order", {"symbol": "BTCUSDT"}, now_ms=0)


def test_connection_reset_propagates():
    c = client([drop_connection()])
    with pytest.raises(ConnectionResetError):
        c.signed("GET", "/fapi/v1/order", {}, now_ms=0)


def test_delay_is_actually_applied():
    c = client([delay(0.05, ok({"orderId": 1}))])
    t0 = time.monotonic()
    c.signed("POST", "/fapi/v1/order", {}, now_ms=0)
    assert time.monotonic() - t0 >= 0.05


def test_malformed_body_becomes_a_typed_error():
    c = client([malformed()])
    with pytest.raises(TestnetError, match="JSON"):
        c.signed("GET", "/fapi/v1/order", {}, now_ms=0)


def test_error_codes_are_classified():
    c = client([err(400, -2022, "ReduceOnly Order is rejected")])
    with pytest.raises(TestnetError) as e:
        c.signed("POST", "/fapi/v1/order", {}, now_ms=0)
    assert e.value.code == -2022

    c = client([err(503, -1001, "Unknown error")])
    with pytest.raises(TestnetError) as e:
        c.signed("POST", "/fapi/v1/order", {}, now_ms=0)
    assert e.value.unknown_execution is True


def test_unexpected_extra_request_is_caught_not_ignored():
    """Sıradaki cevap bittiğinde sessizce devam etmek yerine testi kırar."""
    c = client([ok({})])
    c.signed("GET", "/fapi/v1/order", {}, now_ms=0)
    with pytest.raises(AssertionError, match="beklenmeyen istek"):
        c.signed("GET", "/fapi/v1/order", {}, now_ms=0)


def test_calls_record_method_path_query_and_headers():
    c = client([ok({})])
    c.signed("DELETE", "/fapi/v1/algoOrder", {"clientAlgoId": "p1-SL-v1"}, now_ms=7)
    m, path, q, hdr = c.http.calls[0]
    assert m == "DELETE" and path == "/fapi/v1/algoOrder"
    assert "clientAlgoId=p1-SL-v1" in q and "timestamp=7" in q and "signature=" in q
    assert hdr["X-MBX-APIKEY"] == CREDS.api_key
    assert c.http.paths == ["/fapi/v1/algoOrder"]
