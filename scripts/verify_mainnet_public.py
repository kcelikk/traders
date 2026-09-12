"""Mainnet doğrulaması — **imzasız uçlar**. Emir göndermez, anahtar kullanmaz, para riski yoktur.

Testnet sonucu mainnet için kanıt değildir (Gate 0 §1). Bu betik, anahtar gerektirmeyen her şeyi
mainnet'e karşı ölçer:

  · sembol filtreleri: `tickSize` / `stepSize` / `minNotional` ve `pricePrecision` ile uyuşmaları
  · borsa rate limit değerleri (kodda sabitlenmiş testnet değerleriyle karşılaştırma)
  · saat sapması (`/fapi/v1/time`)
  · koşullu emir uçlarının varlığı (imzasız çağrıda beklenen hata kodu)

İmzalı uçlar (listenKey, pozisyon modu, çoklu varlık teminatı, bakiye) ve `-4130` davranışı
**mainnet anahtarı gerektirir**; bu makinede mainnet anahtarı yok ve bu bilinçli bir duruş
(CLAUDE.md güvenlik bölümü).

Kullanım: PYTHONPATH=. python -m scripts.verify_mainnet_public [--out docs/mainnet-public.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from fbot.core.rounding import _decimals
from fbot.gateway.rest import get

SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
# Kodda sabitlenmiş testnet değerleri (fbot/gateway/testnet.py): mainnet ile aynı mı?
TESTNET_LIMITS = {"REQUEST_WEIGHT_1M": 6000, "ORDERS_10S": 300, "ORDERS_1M": 1200}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    out: dict = {"kaynak": "fapi.binance.com (mainnet, imzasız)", "zaman": int(time.time() * 1000)}

    t0 = time.time() * 1000
    st, _, body = get("/fapi/v1/time")
    t1 = time.time() * 1000
    srv = json.loads(body)["serverTime"]
    out["saat"] = {"status": st, "sapma_ms": round(srv - (t0 + t1) / 2, 1), "rtt_ms": round(t1 - t0, 1)}

    st, _, body = get("/fapi/v1/exchangeInfo")
    ex = json.loads(body)
    limits = {}
    for r in ex.get("rateLimits", []):
        key = f"{r['rateLimitType']}_{r['intervalNum']}{r['interval'][0]}"
        limits[key] = r["limit"]
    out["rate_limits"] = limits
    out["rate_limit_karsilastirma"] = {
        "REQUEST_WEIGHT_1M": {"kodda": TESTNET_LIMITS["REQUEST_WEIGHT_1M"], "mainnet": limits.get("REQUEST_WEIGHT_1M")},
        "ORDERS_10S": {"kodda": TESTNET_LIMITS["ORDERS_10S"], "mainnet": limits.get("ORDERS_10S")},
        "ORDERS_1M": {"kodda": TESTNET_LIMITS["ORDERS_1M"], "mainnet": limits.get("ORDERS_1M")}}

    filt = {}
    for s in ex["symbols"]:
        if s["symbol"] not in SYMBOLS:
            continue
        f = {x["filterType"]: x for x in s["filters"]}
        tick = Decimal(f["PRICE_FILTER"]["tickSize"])
        step = Decimal(f["LOT_SIZE"]["stepSize"])
        filt[s["symbol"]] = {
            "tickSize": str(tick), "stepSize": str(step),
            "minQty": f["LOT_SIZE"]["minQty"], "minNotional": f["MIN_NOTIONAL"]["notional"],
            "pricePrecision": s["pricePrecision"], "quantityPrecision": s["quantityPrecision"],
            # Gate 0 §4: testnet'te tickSize 0,10 · pricePrecision 2 uyuşmuyordu. Mainnet'te?
            "tick_precision_uyusuyor": _decimals(tick) == s["pricePrecision"],
            "step_precision_uyusuyor": _decimals(step) == s["quantityPrecision"],
            "positionSide_destegi": s.get("underlyingType"), "durum": s["status"]}
    out["filtreler"] = filt

    # Koşullu emir ucu: imzasız çağrıda kimlik hatası bekleriz (-2014/-1102). Uç yoksa 404 döner.
    st, _, body = get("/fapi/v1/openAlgoOrders")
    try:
        d = json.loads(body)
    except ValueError:
        d = {"raw": body[:120].decode(errors="replace")}
    out["algo_ucu"] = {"status": st, "code": d.get("code"), "msg": str(d.get("msg"))[:120],
                       "var_mi": st != 404}

    text = json.dumps(out, ensure_ascii=False, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
