from decimal import Decimal

from fbot.core.commands import CancelAlgo, PlaceAlgo, PlaceOrder, canonical


def test_order_commands_canonical():
    po = PlaceOrder(symbol="BTCUSDT", side="SELL", type="MARKET", qty=Decimal("0.001"), price=None, reduce_only=True, client_id="p1-X-v1", time_in_force=None)
    assert canonical(po) == b"PlaceOrder|BTCUSDT|SELL|MARKET|0.001|None|1|p1-X-v1|None"
    pa = PlaceAlgo(symbol="BTCUSDT", side="SELL", type="STOP_MARKET", trigger_price=Decimal("77000.0"), close_position=True,
                   working_type="MARK_PRICE", price_protect=True, client_algo_id="p1-SL-v1")
    assert canonical(pa).startswith(b"PlaceAlgo|BTCUSDT|SELL|STOP_MARKET|77000.0|1|MARK_PRICE|1|p1-SL-v1")
    assert canonical(CancelAlgo(symbol="BTCUSDT", client_algo_id="p1-SL-v1")) == b"CancelAlgo|BTCUSDT|p1-SL-v1"
