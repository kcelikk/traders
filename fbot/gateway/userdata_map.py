"""User data stream olayları → çekirdek `exec` olayları. Saf (dict → dict). Alanlar: docs/binance-api-verification.md §12."""
from __future__ import annotations

_ALGO = {"NEW": "algo_ack", "TRIGGERING": "algo_triggering", "TRIGGERED": "algo_triggered", "FINISHED": "algo_finished",
         "CANCELED": "algo_canceled", "REJECTED": "algo_rejected", "EXPIRED": "algo_rejected"}


def map_user_event(msg: dict) -> dict | None:
    e = msg.get("e")
    if e == "listenKeyExpired":
        return {"kind": "listen_key_expired"}
    if e == "ORDER_TRADE_UPDATE":
        o = msg["o"]
        base = {"client_id": o["c"], "symbol": o["s"], "status": o["X"], "t_ms": o.get("T", msg.get("T"))}
        if o.get("x") == "TRADE":
            return {"kind": "order_fill", **base, "price": o["L"], "qty": o["l"], "cum_qty": o["z"], "reduce_only": bool(o.get("R")),
                    "is_maker": bool(o.get("m")), "commission": o.get("n"), "realized_pnl": o.get("rp"),
                    **({"liquidation": True} if str(o["c"]).startswith(("autoclose-", "adl_autoclose")) else {})}
        if o["X"] in ("NEW", "PARTIALLY_FILLED"):
            return {"kind": "order_ack", **base}
        return {"kind": "order_done", **base, "expiry_reason": o.get("er")}
    if e == "ALGO_UPDATE":
        o = msg["o"]
        kind = _ALGO.get(o["X"])
        if kind is None:
            return None
        return {"kind": kind, "client_algo_id": o["caid"], "algo_id": o.get("aid"), "symbol": o["s"], "status": o["X"],
                "trigger_price": o.get("tp"), "order_id": o.get("ai") or None, "reason": o.get("rm") or None, "t_ms": msg.get("T")}
    return None
