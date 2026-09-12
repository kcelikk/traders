"""Testnet execution adapter: çekirdek komutlarını REST çağrılarına çevirir, cevapları exec olayına döndürür.

İzolasyon kuralı: silahlanma kapıları kapalıyken hiçbir istek gönderilmez (ADR 0015 §3).
"""
from decimal import Decimal as D

import pytest

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder
from fbot.core.position import Filters
from fbot.execution.testnet_adapter import MissingFilters, TestnetAdapter, TestnetDisarmed
from fbot.gateway.signing import Credentials
from fbot.gateway.testnet import TestnetClient, TestnetError
from tests.fake import FakeHTTP


def adapter(responses, armed=True):
    c = TestnetClient(Credentials(api_key="K", api_secret="S"), http=FakeHTTP(responses))
    # Gate 2.0: kaynak borsa filtresi; BTCUSDT'de tickSize 0,10 · pricePrecision 2 uyuşmuyor
    return TestnetAdapter(c, armed=armed,
                          symbols={"BTCUSDT": Filters(step_size=D("0.001"), min_qty=D("0.001"),
                                                      min_notional=D("5"), tick_size=D("0.10"))})


def test_disarmed_adapter_refuses_every_command():
    a = adapter([], armed=False)
    with pytest.raises(TestnetDisarmed):
        a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("0.001"), None, False, "e1", None), now_ms=0)
    assert a.client.http.calls == []


def test_market_order_maps_to_rest_params():
    a = adapter([(200, {}, b'{"orderId":1,"status":"NEW","clientOrderId":"e1"}')])
    out = a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("0.001"), None, False, "e1", None), now_ms=1700000000000)
    _, path, q, _hdr = a.client.http.calls[0]
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
    _, path, q, _hdr = a.client.http.calls[0]
    assert path == "/fapi/v1/algoOrder" and "algoType=CONDITIONAL" in q
    assert "triggerPrice=77000.5" in q and "closePosition=true" in q and "workingType=MARK_PRICE" in q
    assert "priceProtect=true" in q and "clientAlgoId=p1-SL-v1" in q
    assert "quantity" not in q and "reduceOnly" not in q      # closePosition ile birlikte gönderilemez
    assert out["kind"] == "algo_ack" and out["client_algo_id"] == "p1-SL-v1"


def test_cancel_algo():
    a = adapter([(200, {}, b'{"algoStatus":"CANCELED"}')])
    out = a.submit(CancelAlgo("BTCUSDT", "p1-SL-v1"), now_ms=0)
    m, path, q, _hdr = a.client.http.calls[0]
    assert m == "DELETE" and path == "/fapi/v1/algoOrder" and "clientAlgoId=p1-SL-v1" in q
    assert out["kind"] == "algo_canceled"


def test_expected_rejection_is_returned_not_raised():
    """Yarış durumunun normal sonucu olan retler olay döner, alarm üretmez."""
    a = adapter([(400, {}, b'{"code":-2011,"msg":"Unknown order sent."}')])
    out = a.submit(PlaceOrder("BTCUSDT", "SELL", "MARKET", D("0.001"), None, True, "p1-X-v1", None), now_ms=0)
    assert out["kind"] == "order_rejected" and out["code"] == -2011 and out["expected"] is True


def test_reduce_only_rejection_is_unknown_execution_not_a_quiet_success():
    """ADR 0020: -2022 "pozisyon zaten kapalı" demek değildir; mutabakat çözer."""
    a = adapter([(400, {}, b'{"code":-2022,"msg":"ReduceOnly Order is rejected."}')])
    out = a.submit(PlaceOrder("BTCUSDT", "SELL", "MARKET", D("0.001"), None, True, "p1-X-v1", None), now_ms=0)
    assert out["kind"] == "order_unknown" and out["code"] == -2022 and out["needs_reconcile"] is True


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


def test_trigger_price_is_formatted_from_the_tick_not_the_precision():
    """Gate 0 §4: BTCUSDT testnet'te tickSize 0,10 · pricePrecision 2. Precision'a biçimlendirmek
    tick'e oturmayan tetik üretiyordu."""
    a = adapter([(200, {}, b'{"algoId":9,"algoStatus":"NEW"}')])
    a.submit(PlaceAlgo("BTCUSDT", "SELL", "STOP_MARKET", D("74960.70"), True, "MARK_PRICE", True, "p1-SL-v1"), now_ms=0)
    _, _, q, _ = a.client.http.calls[0]
    assert "triggerPrice=74960.7" in q


def test_trigger_price_off_the_tick_is_refused_before_it_reaches_the_exchange():
    """Yuvarlama çekirdeğin işi; adapter sessizce düzeltmez, hata verir."""
    a = adapter([(200, {}, b'{"algoId":9}')])
    with pytest.raises(ValueError, match="tick"):
        a.submit(PlaceAlgo("BTCUSDT", "SELL", "STOP_MARKET", D("74960.75"), True, "MARK_PRICE", True, "p1-SL-v1"), now_ms=0)
    assert a.client.http.calls == []


def test_quantity_is_floored_to_the_step():
    a = adapter([(200, {}, b'{"orderId":1,"status":"NEW"}')])
    a.submit(PlaceOrder("BTCUSDT", "BUY", "MARKET", D("0.0019"), None, False, "e1", None), now_ms=0)
    _, _, q, _ = a.client.http.calls[0]
    assert "quantity=0.001" in q


def test_unknown_symbol_is_fail_closed():
    a = adapter([])
    with pytest.raises(MissingFilters):
        a.submit(PlaceOrder("ETHUSDT", "BUY", "MARKET", D("1"), None, False, "e1", None), now_ms=0)
    assert a.client.http.calls == []
