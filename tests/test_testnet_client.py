"""Testnet REST istemcisi: yalnızca testnet uçları, silahlanma kapıları, rate limit ve hata eşlemesi."""
import pytest

from fbot.gateway.signing import Credentials
from fbot.gateway.testnet import BASE, TestnetClient, TestnetError
from tests.fake import FakeHTTP


CREDS = Credentials(api_key="KEY1234567890", api_secret="SECRET")


def client(responses, **kw):
    return TestnetClient(CREDS, http=FakeHTTP(responses), **kw)


def test_base_url_is_testnet_only_and_mainnet_absent():
    assert BASE == "https://testnet.binancefuture.com"
    src = open("fbot/gateway/testnet.py").read()
    assert "fapi.binance.com" not in src, "mainnet URL testnet modülünde bulunmamalı"


def test_signed_request_sends_key_header_and_signature():
    c = client([(200, {}, b'{"ok":1}')])
    c.signed("POST", "/fapi/v1/order", {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.001"}, now_ms=1700000000000)
    method, path, query, headers = c.http.calls[0]
    assert method == "POST" and path == "/fapi/v1/order"
    assert headers["X-MBX-APIKEY"] == "KEY1234567890"
    assert "signature=" in query and "timestamp=1700000000000" in query and "recvWindow=" in query


def test_rate_limiter_is_synced_from_headers():
    c = client([(200, {"x-mbx-order-count-10s": "297", "x-mbx-used-weight-1m": "100"}, b"{}")])
    c.signed("POST", "/fapi/v1/order", {"symbol": "X"}, now_ms=0)
    assert c.limiter.remaining(0)["orders_10s"] == 3


def test_429_triggers_backoff_and_blocks_next_order():
    c = client([(429, {}, b'{"code":-1003}'), (200, {}, b"{}")])
    with pytest.raises(TestnetError) as e:
        c.place_order({"symbol": "X", "side": "BUY", "type": "MARKET", "quantity": "1"}, now_ms=1000)
    assert e.value.status == 429
    with pytest.raises(TestnetError, match="rate limit"):
        c.place_order({"symbol": "X", "side": "BUY", "type": "MARKET", "quantity": "1"}, now_ms=2000)


def test_418_sets_banned():
    c = client([(418, {}, b"{}")])
    with pytest.raises(TestnetError):
        c.place_order({"symbol": "X", "side": "BUY", "type": "MARKET", "quantity": "1"}, now_ms=0)
    assert c.limiter.banned


def test_503_unknown_status_is_flagged_not_failed():
    """Doğrulanmış kural: 503 'Unknown error' başarısız sayılmaz, yürütme durumu BİLİNMİYOR."""
    c = client([(503, {}, b'{"code":-1001,"msg":"Unknown error"}')])
    with pytest.raises(TestnetError) as e:
        c.place_order({"symbol": "X", "side": "BUY", "type": "MARKET", "quantity": "1"}, now_ms=0)
    assert e.value.unknown_execution is True


def test_error_codes_are_mapped():
    c = client([(400, {}, b'{"code":-2022,"msg":"ReduceOnly Order is rejected."}')])
    with pytest.raises(TestnetError) as e:
        c.place_order({"symbol": "X", "side": "SELL", "type": "MARKET", "quantity": "1", "reduceOnly": "true"}, now_ms=0)
    assert e.value.code == -2022 and e.value.expected is True     # beklenen ret (yarış durumu), alarm değil


def test_algo_order_uses_algo_endpoint_and_trigger_price():
    c = client([(200, {}, b'{"algoId":1}')])
    c.place_algo({"symbol": "X", "side": "SELL", "type": "STOP_MARKET", "triggerPrice": "100", "closePosition": "true"}, now_ms=0)
    method, path, query, _ = c.http.calls[0]
    assert path == "/fapi/v1/algoOrder" and "algoType=CONDITIONAL" in query and "triggerPrice=100" in query


def test_order_budget_reserved_for_protection():
    c = client([(200, {}, b"{}")], reserve_orders=3)
    c.limiter.o10.override = c.limiter.limits.orders_10s - 2      # yalnızca 2 emir kaldı
    with pytest.raises(TestnetError, match="rate limit"):
        c.place_order({"symbol": "X", "side": "BUY", "type": "MARKET", "quantity": "1"}, now_ms=0, entry=True)
    c.place_order({"symbol": "X", "side": "SELL", "type": "MARKET", "quantity": "1", "reduceOnly": "true"}, now_ms=0, entry=False)
