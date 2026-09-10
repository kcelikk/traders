"""Sembol evreni kuralı (ADR 0004). Saf."""
from __future__ import annotations

STABLE_BASES = frozenset({"USDC", "FDUSD", "TUSD", "BUSD", "USD1", "USDE", "USDP", "DAI", "USDT"})


def select_top(symbols_info: list[dict], tickers: list[dict], n: int, exclude_bases=STABLE_BASES, quote: str = "USDT") -> list[str]:
    """USDT-margined PERPETUAL, TRADING, stablecoin base hariç; 24 s quoteVolume'a göre azalan. Deterministik: eşitlikte sembol adı."""
    ok = {
        s["symbol"]
        for s in symbols_info
        if s.get("contractType") == "PERPETUAL" and s.get("status") == "TRADING"
        and s.get("quoteAsset") == quote and s.get("baseAsset") not in exclude_bases
    }
    ranked = sorted(
        ((float(t["quoteVolume"]), t["symbol"]) for t in tickers if t["symbol"] in ok),
        key=lambda x: (-x[0], x[1]),
    )
    return [sym for _, sym in ranked[:n]]


def symbol_filters(sym_info: dict) -> dict:
    """Emir doğrulama için gereken filtreler; ondalık hassasiyet için string bırakılır."""
    f = {x["filterType"]: x for x in sym_info["filters"]}
    return {
        "tick_size": f["PRICE_FILTER"]["tickSize"],
        "step_size": f["LOT_SIZE"]["stepSize"],
        "min_qty": f["LOT_SIZE"]["minQty"],
        "min_notional": f["MIN_NOTIONAL"]["notional"],
        "price_precision": sym_info["pricePrecision"],
        "quantity_precision": sym_info["quantityPrecision"],
    }
