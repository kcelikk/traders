import json
from pathlib import Path

from fbot.universe import select_top, symbol_filters, STABLE_BASES

FX = Path(__file__).parent / "fixtures"
EX = json.load(open(FX / "exchange_info_small.json"))["symbols"]
TK = json.load(open(FX / "ticker24h_small.json"))


def test_select_top_excludes_stablecoins_delivery_and_non_trading():
    top = select_top(EX, TK, n=10, exclude_bases=STABLE_BASES)
    assert "USDCUSDT" not in top          # stablecoin base
    assert "BTCUSDT_260925" not in top    # delivery kontratı
    assert "XYZUSDT" not in top           # PENDING_TRADING (hacmi en yüksek olsa da)
    assert top[:2] == ["BTCUSDT", "ETHUSDT"]  # hacim sırası


def test_select_top_respects_n_and_is_deterministic():
    a = select_top(EX, TK, n=3, exclude_bases=STABLE_BASES)
    b = select_top(list(reversed(EX)), list(reversed(TK)), n=3, exclude_bases=STABLE_BASES)
    assert a == b and len(a) == 3


def test_symbol_filters_extracts_decimals():
    btc = next(s for s in EX if s["symbol"] == "BTCUSDT")
    f = symbol_filters(btc)
    assert f["tick_size"] == "0.10" and f["step_size"] == "0.001"
    assert f["min_qty"] == "0.001" and f["min_notional"] == "50"
