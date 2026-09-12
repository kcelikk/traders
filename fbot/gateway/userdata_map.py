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
        # `t` = tradeId (0 = işlem yok), `i` = orderId. İkisi de Gate 3b'de kayda alınan gerçek
        # çerçevelerde vardı ama eşleyici okumuyordu: `OrderBook.apply` dedupe için `trade_id`'yi
        # arıyor, bulamadığı için tekrar bastırma sessizce çalışmıyordu.
        base = {"client_id": o["c"], "symbol": o["s"], "status": o["X"], "t_ms": o.get("T", msg.get("T")),
                "order_id": o.get("i")}
        if o.get("x") == "TRADE":
            tid = o.get("t")
            return {"kind": "order_fill", **base, "trade_id": tid if tid else None,
                    "price": o["L"], "qty": o["l"], "cum_qty": o["z"], "reduce_only": bool(o.get("R")),
                    "is_maker": bool(o.get("m")), "commission": o.get("n"), "realized_pnl": o.get("rp"),
                    **({"liquidation": True} if str(o["c"]).startswith(("autoclose-", "adl_autoclose")) else {})}
        if o["X"] in ("NEW", "PARTIALLY_FILLED"):
            return {"kind": "order_ack", **base}
        return {"kind": "order_done", **base, "expiry_reason": o.get("er")}
    if e == "TRADE_LITE":
        # Gate 0 §2: dokümanda yok, `ORDER_TRADE_UPDATE`'ten **önce** gelen hafif dolum bildirimi.
        # Aynı bilgi ORDER_TRADE_UPDATE'te var; burada bilinçli olarak yok sayılır (çift sayım olmasın)
        # ama görünür kalsın diye kendi kindi verilir.
        return {"kind": "trade_lite", "client_id": msg.get("c"), "symbol": msg.get("s"),
                "price": msg.get("L"), "qty": msg.get("l"), "trade_id": msg.get("t") or None,
                "order_id": msg.get("i"), "is_maker": bool(msg.get("m")), "t_ms": msg.get("T")}
    if e == "ACCOUNT_UPDATE":
        # Gate 0 §2'de alanları doğrulandı. `a.m` tetikleyen neden, `a.P[].pa` işaretli miktar.
        a = msg.get("a") or {}
        return {"kind": "account_update", "reason": a.get("m"), "t_ms": msg.get("T"),
                "balances": [{"asset": b.get("a"), "wallet": b.get("wb"), "cross": b.get("cw"),
                              "change": b.get("bc")} for b in (a.get("B") or [])],
                "positions": [{"symbol": p.get("s"), "qty": p.get("pa"), "entry_price": p.get("ep"),
                               "breakeven": p.get("bep"), "realized": p.get("cr"), "unrealized": p.get("up"),
                               "margin_type": p.get("mt"), "position_side": p.get("ps")} for p in (a.get("P") or [])]}
    if e == "ACCOUNT_CONFIG_UPDATE":
        ac = msg.get("ac") or {}
        return {"kind": "account_config", "symbol": ac.get("s"), "leverage": ac.get("l"), "t_ms": msg.get("T")}
    if e == "MARGIN_CALL":
        return {"kind": "margin_call", "t_ms": msg.get("T"),
                "positions": [{"symbol": p.get("s"), "qty": p.get("pa"), "margin_type": p.get("mt"),
                               "maint_margin": p.get("mm"), "unrealized": p.get("up")} for p in (msg.get("p") or [])]}
    if e == "ALGO_UPDATE":
        o = msg["o"]
        kind = _ALGO.get(o["X"])
        if kind is None:
            return None
        return {"kind": kind, "client_algo_id": o["caid"], "algo_id": o.get("aid"), "symbol": o["s"], "status": o["X"],
                "trigger_price": o.get("tp"), "order_id": o.get("ai") or None, "reason": o.get("rm") or None, "t_ms": msg.get("T")}
    return None
