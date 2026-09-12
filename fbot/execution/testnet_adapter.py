"""Testnet execution adapter (Faz 9, ADR 0015): çekirdek komutları → testnet REST çağrıları.

Çekirdek saf kalır; bu modül I/O kenarıdır. Silahlanma kapıları kapalıyken **hiçbir istek gönderilmez**.
Beklenen retler (yarış durumu sonuçları) olay olarak döner, istisna fırlatmaz; beklenmeyen hatalar fırlatır.
"""
from __future__ import annotations


from fbot.core.commands import CancelAlgo, CancelOrder, PlaceAlgo, PlaceOrder
from fbot.core.rounding import fmt_price, fmt_qty
from fbot.gateway.testnet import TestnetClient, TestnetError


class TestnetDisarmed(RuntimeError):
    pass


class MissingFilters(RuntimeError):
    """Sembolün borsa filtresi yoksa emir gönderilmez (fail-closed). Precision'a düşmek tick'e
    oturmayan fiyat üretir (Gate 0 §4: BTCUSDT tickSize 0,10 · pricePrecision 2)."""


class TestnetAdapter:
    """`symbols`: sembol → `Filters` (step_size / tick_size). `pricePrecision` **kullanılmaz**."""

    def __init__(self, client: TestnetClient, armed: bool, symbols: dict | None = None):
        self.client = client
        self.armed = armed
        self.symbols = symbols or {}

    def rearm(self, client, armed: bool) -> None:
        """Anahtar değişince çalışırken silahlanma/silahsızlanma (ArmingSupervisor çağırır).
        Silahsızlanınca istemci de düşürülür: eski anahtarla istek gönderilemez."""
        self.client = client
        self.armed = bool(armed and client is not None)

    def _filters(self, symbol: str):
        f = self.symbols.get(symbol)
        if f is None:
            raise MissingFilters(f"{symbol} için borsa filtresi yok: emir gönderilmez (fail-closed)")
        return f

    def submit(self, cmd, now_ms: int) -> dict:
        if not self.armed:
            raise TestnetDisarmed("testnet silahlanmadı: FBOT_TESTNET_ARMED + anahtar + mode=testnet gerekir")
        if isinstance(cmd, PlaceOrder):
            return self._order(cmd, now_ms)
        if isinstance(cmd, PlaceAlgo):
            return self._algo(cmd, now_ms)
        if isinstance(cmd, CancelAlgo):
            return self._cancel_algo(cmd, now_ms)
        if isinstance(cmd, CancelOrder):
            return self._cancel_order(cmd, now_ms)
        raise TypeError(f"desteklenmeyen komut: {type(cmd).__name__}")

    # İptal cevabı **doğrulanır**: "istek gitti" ile "emir gerçekten iptal oldu" aynı şey değildir.
    # Doğrulanmamış iptal, koruma emrinin borsada durduğu hâlde iç durumda yok sayılmasına yol açar.
    CANCEL_OK = ("CANCELED", "FINISHED", "EXPIRED")

    def _cancel_algo(self, c: CancelAlgo, now_ms: int) -> dict:
        base = {"client_algo_id": c.client_algo_id, "symbol": c.symbol}
        try:
            r = self.client.cancel_algo({"symbol": c.symbol, "clientAlgoId": c.client_algo_id}, now_ms) or {}
        except TestnetError as e:
            return self._error_event(e, {"kind": "algo_cancel", **base})
        status = r.get("algoStatus") or r.get("status")
        if status is not None and status not in self.CANCEL_OK:
            # Borsa iptali onaylamadı: emir hâlâ duruyor olabilir → mutabakat çözsün
            return {"kind": "algo_cancel_unknown", **base, "status": status, "needs_reconcile": True}
        return {"kind": "algo_canceled", **base, "status": status}

    def _cancel_order(self, c: CancelOrder, now_ms: int) -> dict:
        base = {"client_id": c.client_id, "symbol": c.symbol}
        try:
            r = self.client.cancel_order({"symbol": c.symbol, "origClientOrderId": c.client_id}, now_ms) or {}
        except TestnetError as e:
            return self._error_event(e, {"kind": "order_cancel", **base})
        status = r.get("status")
        if status is not None and status not in self.CANCEL_OK:
            return {"kind": "order_cancel_unknown", **base, "status": status, "needs_reconcile": True}
        return {"kind": "order_canceled", **base, "status": status}

    def _order(self, c: PlaceOrder, now_ms: int) -> dict:
        f = self._filters(c.symbol)
        # `positionSide` açıkça gönderilir: hesap HEDGE'e alınmışsa varsayılana güvenmek yanlış
        # tarafa emir yazar (kilitli karar: ONE-WAY, ADR 0004).
        p = {"symbol": c.symbol, "side": c.side, "type": c.type, "positionSide": "BOTH",
             "quantity": fmt_qty(c.qty, f.step_size),
             "newClientOrderId": c.client_id}
        if c.reduce_only:
            p["reduceOnly"] = "true"
        if c.price is not None:
            p["price"] = fmt_price(c.price, f.tick_size)
        if c.time_in_force:
            p["timeInForce"] = c.time_in_force
        try:
            r = self.client.place_order(p, now_ms, entry=not c.reduce_only)
        except TestnetError as e:
            return self._error_event(e, {"kind": "order", "client_id": c.client_id, "symbol": c.symbol})
        return {"kind": "order_ack", "client_id": c.client_id, "symbol": c.symbol,
                "order_id": r.get("orderId"), "status": r.get("status")}

    def _algo(self, c: PlaceAlgo, now_ms: int) -> dict:
        # closePosition=true ile quantity ve reduceOnly gönderilemez (hata -4137/-4138)
        p = {"symbol": c.symbol, "side": c.side, "type": c.type, "positionSide": "BOTH",
             "triggerPrice": fmt_price(c.trigger_price, self._filters(c.symbol).tick_size),
             "closePosition": "true" if c.close_position else "false",
             "workingType": c.working_type, "priceProtect": "true" if c.price_protect else "false",
             "clientAlgoId": c.client_algo_id}
        try:
            r = self.client.place_algo(p, now_ms)
        except TestnetError as e:
            return self._error_event(e, {"kind": "algo", "client_algo_id": c.client_algo_id, "symbol": c.symbol})
        return {"kind": "algo_ack", "client_algo_id": c.client_algo_id, "symbol": c.symbol,
                "algo_id": r.get("algoId"), "status": r.get("algoStatus")}

    @staticmethod
    def _error_event(e: TestnetError, base: dict) -> dict:
        kind = base.pop("kind")
        if e.unknown_execution:
            return {"kind": f"{kind}_unknown", **base, "code": e.code, "msg": str(e), "needs_reconcile": True}
        if e.expected:
            return {"kind": f"{kind}_rejected", **base, "code": e.code, "msg": str(e), "expected": True}
        raise e
