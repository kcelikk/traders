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


def test_post_timeout_becomes_unknown_execution():
    """Gate 2.1: POST'ta zaman aşımı "gönderilmedi" demek değildir; emir gerçekleşmiş olabilir.
    Yürütme durumu bilinmiyor → mutabakat gerekir."""
    c = client([timeout()])
    with pytest.raises(TestnetError) as e:
        c.signed("POST", "/fapi/v1/order", {"symbol": "BTCUSDT"}, now_ms=0)
    assert e.value.unknown_execution is True and "zaman aşımı" in str(e.value)


def test_read_timeout_is_not_unknown_execution():
    """GET idempotenttir ve hiçbir şey yürütmez; UNKNOWN işaretlemek gereksiz mutabakat kilidi üretir."""
    c = client([timeout()])
    with pytest.raises(TestnetError) as e:
        c.signed("GET", "/fapi/v1/positionRisk", {}, now_ms=0)
    assert e.value.unknown_execution is False


def test_connection_reset_is_classified_by_method():
    c = client([drop_connection()])
    with pytest.raises(TestnetError) as e:
        c.signed("GET", "/fapi/v1/order", {}, now_ms=0)
    assert e.value.unknown_execution is False
    c = client([drop_connection()])
    with pytest.raises(TestnetError) as e:
        c.signed("POST", "/fapi/v1/order", {}, now_ms=0)
    assert e.value.unknown_execution is True


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
