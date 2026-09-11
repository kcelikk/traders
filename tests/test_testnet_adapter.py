"""Testnet execution adapter: çekirdek komutlarını REST çağrılarına çevirir, cevapları exec olayına döndürür.

İzolasyon kuralı: silahlanma kapıları kapalıyken hiçbir istek gönderilmez (ADR 0015 §3).
"""
from decimal import Decimal as D

import pytest

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder
from fbot.execution.testnet_adapter import TestnetAdapter, TestnetDisarmed
from fbot.gateway.signing import Credentials
from fbot.gateway.testnet import TestnetClient, TestnetError


class FakeHTTP:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, method, path, query, headers, timeout):
        self.calls.append((method, path, query))
        r = self.responses.pop(0)
        return r() if callable(r) else r


def adapter(responses, armed=True):
    c = TestnetClient(Credentials(api_key="K", api_secret="S"), http=FakeHTTP(responses))
    return TestnetAdapter(c, armed=armed, symbols={"BTCUSDT": {"pricePrecision": 2, "quantityPrecision": 3}})


def test_disarmed_adapter_refuses_every_command():
    a = adapter([], armed=False)
    with pytest.raises(TestnetDisarmed):
        a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("0.001"), None, False, "e1", None), now_ms=0)
    assert a.client.http.calls == []


def test_market_order_maps_to_rest_params():
    a = adapter([(200, {}, b'{"orderId":1,"status":"NEW","clientOrderId":"e1"}')])
    out = a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("0.001"), None, False, "e1", None), now_ms=1700000000000)
    _, path, q = a.client.http.calls[0]
    assert path == "/fapi/v1/order"
    assert "symbol=BTCUSDT" in q and "side=BUY" in q and "type=MARKET" in q and "quantity=0.001" in q
    assert "newClientOrderId=e1" in q and "reduceOnly" not in q
    assert out["kind"] == "order_ack" and out["client_id"] == "e1"


def test_reduce_only_exit_sets_flag():
    a = adapter([(200, {}, b'{"orderId":2,"status":"NEW"}')])
    a.submit(PlaceOrder("BTCUSDT", "SELL", "MARKET", D("0.001"), None, True, "p1-X-v1", None), now_ms=0)
    assert "reduceOnly=true" in a.client.http.calls[0][2]


def test_algo_order_uses_trigger_price_and_close_position():
    a = adapter([(200, {}, b'{"algoId":9,"clientAlgoId":"p1-SL-v1","algoStatus":"NEW"}')])
    out = a.submit(PlaceAlgo("BTCUSDT", "SELL", "STOP_MARKET", D("77000.5"), True, "MARK_PRICE", True, "p1-SL-v1"), now_ms=0)
    _, path, q = a.client.http.calls[0]
    assert path == "/fapi/v1/algoOrder" and "algoType=CONDITIONAL" in q
    assert "triggerPrice=77000.5" in q and "closePosition=true" in q and "workingType=MARK_PRICE" in q
    assert "priceProtect=true" in q and "clientAlgoId=p1-SL-v1" in q
    assert "quantity" not in q and "reduceOnly" not in q      # closePosition ile birlikte gönderilemez
    assert out["kind"] == "algo_ack" and out["client_algo_id"] == "p1-SL-v1"


def test_cancel_algo():
    a = adapter([(200, {}, b'{"algoStatus":"CANCELED"}')])
    out = a.submit(CancelAlgo("BTCUSDT", "p1-SL-v1"), now_ms=0)
    m, path, q = a.client.http.calls[0]
    assert m == "DELETE" and path == "/fapi/v1/algoOrder" and "clientAlgoId=p1-SL-v1" in q
    assert out["kind"] == "algo_canceled"


def test_expected_rejection_is_returned_not_raised():
    """-2022 reduceOnly reddi yarış durumunun normal sonucudur: alarm değil, olay."""
    a = adapter([(400, {}, b'{"code":-2022,"msg":"ReduceOnly Order is rejected."}')])
    out = a.submit(PlaceOrder("BTCUSDT", "SELL", "MARKET", D("0.001"), None, True, "p1-X-v1", None), now_ms=0)
    assert out["kind"] == "order_rejected" and out["code"] == -2022 and out["expected"] is True


def test_unknown_execution_is_flagged_for_reconciliation():
    a = adapter([(503, {}, b'{"code":-1001,"msg":"Unknown error"}')])
    out = a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("0.001"), None, False, "e1", None), now_ms=0)
    assert out["kind"] == "order_unknown" and out["needs_reconcile"] is True


def test_quantity_is_formatted_to_symbol_precision():
    a = adapter([(200, {}, b'{"orderId":1}')])
    a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("0.0010000"), None, False, "e1", None), now_ms=0)
    assert "quantity=0.001&" in a.client.http.calls[0][2] + "&"


def test_unexpected_error_raises():
    a = adapter([(400, {}, b'{"code":-1121,"msg":"Invalid symbol."}')])
    with pytest.raises(TestnetError):
        a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("0.001"), None, False, "e1", None), now_ms=0)


def test_rearm_swaps_client_and_disarm_blocks_orders():
    a = TestnetAdapter(client=object(), armed=False, symbols={})
    new_client = object()
    a.rearm(new_client, True)
    assert a.client is new_client and a.armed is True
    a.rearm(None, False)
    assert a.armed is False and a.client is None
    with pytest.raises(TestnetDisarmed):
        a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("1"), None, False, "x", None), 0)
