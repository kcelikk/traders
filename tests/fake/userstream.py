"""Binance user data stream olay üreteçleri.

Alanlar `docs/binance-api-verification.md` §12'de doğrulanmış olanlardır. **`ACCOUNT_UPDATE` ve
`listenKeyExpired` alanları henüz testnet'e karşı doğrulanmadı** (aynı dokümanda not düşülmüş);
buradaki şekilleri Gate 3'ün ilk adımında ölçümle güncellenecek ve o zamana kadar yalnız
`ORDER_TRADE_UPDATE` ile `ALGO_UPDATE` üzerine test yazılmalıdır.
"""
from __future__ import annotations

DOGRULANMAMIS = ("ACCOUNT_UPDATE", "listenKeyExpired")


def order_trade_update(client_id: str, symbol: str = "BTCUSDT", status: str = "NEW", exec_type: str = "NEW",
                       last_price: str = "0", last_qty: str = "0", cum_qty: str = "0", trade_id: int | None = None,
                       order_id: int = 1, reduce_only: bool = False, is_maker: bool = False,
                       commission: str | None = None, realized_pnl: str | None = None,
                       t_ms: int = 1_700_000_000_000, expiry_reason: str | None = None) -> dict:
    o = {"s": symbol, "c": client_id, "X": status, "x": exec_type, "i": order_id,
         "L": last_price, "l": last_qty, "z": cum_qty, "R": reduce_only, "m": is_maker, "T": t_ms}
    if trade_id is not None:
        o["t"] = trade_id
    if commission is not None:
        o["n"] = commission
    if realized_pnl is not None:
        o["rp"] = realized_pnl
    if expiry_reason is not None:
        o["er"] = expiry_reason
    return {"e": "ORDER_TRADE_UPDATE", "T": t_ms, "o": o}


def algo_update(client_algo_id: str, status: str = "NEW", symbol: str = "BTCUSDT", side: str = "SELL",
                order_type: str = "STOP_MARKET", trigger_price: str = "78000", algo_id: int = 11,
                triggered_order_id: int | None = None, close_position: bool = True,
                reject_reason: str | None = None, t_ms: int = 1_700_000_000_000) -> dict:
    o = {"caid": client_algo_id, "aid": algo_id, "at": "CONDITIONAL", "o": order_type, "s": symbol,
         "S": side, "X": status, "tp": trigger_price, "cp": close_position, "wt": "MARK_PRICE", "pP": True}
    if triggered_order_id is not None:
        o["ai"] = triggered_order_id
    if reject_reason is not None:
        o["rm"] = reject_reason
    return {"e": "ALGO_UPDATE", "T": t_ms, "o": o}


def account_update(positions=(), balances=(), reason: str = "ORDER", t_ms: int = 1_700_000_000_000) -> dict:
    """DOĞRULANMAMIŞ şekil — Gate 3'ün ilk adımında testnet ölçümüyle güncellenecek."""
    return {"e": "ACCOUNT_UPDATE", "T": t_ms,
            "a": {"m": reason,
                  "P": [{"s": p["symbol"], "pa": p["qty"], "ep": p.get("entry_price", "0"),
                         "up": p.get("unrealized", "0"), "ps": p.get("position_side", "BOTH")} for p in positions],
                  "B": [{"a": b["asset"], "wb": b["wallet"], "cw": b.get("cross", b["wallet"])} for b in balances]}}


def listen_key_expired(t_ms: int = 1_700_000_000_000) -> dict:
    """DOĞRULANMAMIŞ şekil — Gate 3'ün ilk adımında testnet ölçümüyle güncellenecek."""
    return {"e": "listenKeyExpired", "E": t_ms}
