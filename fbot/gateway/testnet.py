"""Binance USDⓈ-M Futures **testnet** REST istemcisi (ADR 0015). I/O kenarı.

Yalnızca testnet: taban URL sabittir, mainnet adresi bu modülde bulunmaz ve config'den verilemez.
İmza HMAC SHA256 (stdlib). Rate limit gerçek header/`rateLimits` değerleriyle senkronlanır;
429 geri çekilme, 418 kalıcı ban (kill switch tetikleyicisi). 503 "Unknown error" başarısız SAYILMAZ:
yürütme durumu bilinmiyordur, mutabakat gerekir (docs/binance-api-verification.md §4).

Testnet tesisat doğrulama ortamıdır; sonuçları kârlılık kanıtı değildir (ADR 0015).
"""
from __future__ import annotations

import http.client
import json
from dataclasses import dataclass

from fbot.core.rate_limit import Limits, RateLimiter
from fbot.gateway.signing import Credentials, sign_query

BASE = "https://testnet.binancefuture.com"
_HOST = BASE.split("://", 1)[1]

# Beklenen retler: yarış durumunun normal sonucu, alarm üretmez (docs/design/faz4-cikis-kurallari.md §9)
EXPECTED_CODES = {-2022, -2011, -2013, -4137, -4138, -1111, -4164, -5021, -5022}
UNKNOWN_EXECUTION = {-1001}


class TestnetError(RuntimeError):
    def __init__(self, msg: str, status: int = 0, code: int | None = None, unknown_execution: bool = False, expected: bool = False):
        super().__init__(msg)
        self.status, self.code = status, code
        self.unknown_execution, self.expected = unknown_execution, expected


def _http(method: str, path: str, query: str, headers: dict, timeout: float):
    conn = http.client.HTTPSConnection(_HOST, timeout=timeout)
    try:
        url = f"{path}?{query}" if query else path
        conn.request(method, url, headers=headers)
        r = conn.getresponse()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
    finally:
        conn.close()


@dataclass
class TestnetClient:
    creds: Credentials
    http: callable = _http
    recv_window: int = 5000
    timeout: float = 10.0
    reserve_orders: int = 3
    limiter: RateLimiter = None

    def __post_init__(self):
        if self.limiter is None:
            # exchangeInfo'dan doğrulandı: testnet REQUEST_WEIGHT 6000/dk, ORDERS 300/10s ve 1200/dk
            self.limiter = RateLimiter(Limits(weight_1m=6000, orders_10s=300, orders_1m=1200),
                                       backoff_ms=10_000, reserve_orders=self.reserve_orders)

    # ---------------- düşük seviye
    def signed(self, method: str, path: str, params: dict, now_ms: int) -> dict:
        p = {**params, "recvWindow": self.recv_window, "timestamp": now_ms}
        q, sig = sign_query(p, self.creds)
        status, headers, body = self.http(method, path, f"{q}&signature={sig}", {"X-MBX-APIKEY": self.creds.api_key}, self.timeout)
        self.limiter.sync_headers(headers, now_ms)
        act = self.limiter.on_response(status, now_ms)
        if status == 200:
            try:
                return json.loads(body or b"{}")
            except ValueError:
                raise TestnetError("cevap JSON değil", status=status)
        code, msg = None, (body or b"")[:200].decode(errors="replace")
        try:
            d = json.loads(body or b"{}")
            code, msg = d.get("code"), d.get("msg", msg)
        except ValueError:
            pass
        raise TestnetError(f"HTTP {status} code={code} {msg}" + (f" [{act}]" if act else ""), status=status, code=code,
                           unknown_execution=(status >= 500 and code in UNKNOWN_EXECUTION) or status == 503,
                           expected=code in EXPECTED_CODES)

    # ---------------- emirler
    def place_order(self, params: dict, now_ms: int, entry: bool = False) -> dict:
        if not self.limiter.allow_order(now_ms, entry=entry):
            raise TestnetError("rate limit: emir bütçesi yok (rezerv koruma emirleri için ayrıldı)", status=0)
        self.limiter.on_order(now_ms)
        return self.signed("POST", "/fapi/v1/order", params, now_ms)

    def place_algo(self, params: dict, now_ms: int, entry: bool = False) -> dict:
        """Koşullu emirler Algo Service'e taşındı (2025-12-09): tetik `triggerPrice`, kimlik `clientAlgoId`."""
        if not self.limiter.allow_order(now_ms, entry=entry):
            raise TestnetError("rate limit: emir bütçesi yok", status=0)
        self.limiter.on_order(now_ms)
        return self.signed("POST", "/fapi/v1/algoOrder", {"algoType": "CONDITIONAL", **params}, now_ms)

    def cancel_order(self, params: dict, now_ms: int) -> dict:
        return self.signed("DELETE", "/fapi/v1/order", params, now_ms)

    def cancel_algo(self, params: dict, now_ms: int) -> dict:
        return self.signed("DELETE", "/fapi/v1/algoOrder", params, now_ms)

    def order_status(self, params: dict, now_ms: int) -> dict:
        return self.signed("GET", "/fapi/v1/order", params, now_ms)

    # ---------------- hesap / mutabakat
    def positions(self, now_ms: int) -> list:
        return self.signed("GET", "/fapi/v2/positionRisk", {}, now_ms)

    def open_orders(self, now_ms: int) -> list:
        return self.signed("GET", "/fapi/v1/openOrders", {}, now_ms)

    def open_algos(self, now_ms: int) -> list:
        return self.signed("GET", "/fapi/v1/openAlgoOrders", {}, now_ms)

    def balance(self, now_ms: int) -> list:
        return self.signed("GET", "/fapi/v2/balance", {}, now_ms)

    def income(self, params: dict, now_ms: int) -> list:
        return self.signed("GET", "/fapi/v1/income", params, now_ms)

    def listen_key(self, now_ms: int) -> str:
        """User data stream: listenKey (ADR 0003). Keepalive private bağlantı yöneticisinin işidir."""
        status, headers, body = self.http("POST", "/fapi/v1/listenKey", "", {"X-MBX-APIKEY": self.creds.api_key}, self.timeout)
        self.limiter.sync_headers(headers, now_ms)
        if status != 200:
            raise TestnetError(f"listenKey HTTP {status}", status=status)
        return json.loads(body)["listenKey"]

    def keepalive_listen_key(self, now_ms: int) -> None:
        self.http("PUT", "/fapi/v1/listenKey", "", {"X-MBX-APIKEY": self.creds.api_key}, self.timeout)
