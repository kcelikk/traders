"""REST istemcisi (stdlib). Yalnızca snapshot / evren çözümleme. Bloklayıcıdır; asyncio.to_thread ile çağrılır."""
from __future__ import annotations

import http.client
import json
import urllib.parse

HOST = "fapi.binance.com"


def get(path: str, params: dict | None = None, timeout: float = 10.0) -> tuple[int, dict, bytes]:
    """(status, headers, body). Rate limit header'ları çağırana döner; tahmini sayaç tutulmaz."""
    q = ("?" + urllib.parse.urlencode(params)) if params else ""
    conn = http.client.HTTPSConnection(HOST, timeout=timeout)
    try:
        conn.request("GET", path + q, headers={"User-Agent": "fbot-recorder"})
        r = conn.getresponse()
        body = r.read()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, body
    finally:
        conn.close()


def exchange_info() -> dict:
    st, _, body = get("/fapi/v1/exchangeInfo")
    if st != 200:
        raise RuntimeError(f"exchangeInfo HTTP {st}")
    return json.loads(body)


def ticker_24h() -> list[dict]:
    st, _, body = get("/fapi/v1/ticker/24hr")
    if st != 200:
        raise RuntimeError(f"ticker/24hr HTTP {st}")
    return json.loads(body)


def depth_raw(symbol: str, limit: int = 1000) -> tuple[int, dict, bytes]:
    """Ham gövde döner; kayda bayt-bayt yazılır."""
    return get("/fapi/v1/depth", {"symbol": symbol, "limit": limit})
