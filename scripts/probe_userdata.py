"""Gate 3b gözlem kanıtı: canlı testnet'te **dolmayacak** bir limit emri koyup iptal eder.

Amaç, shadow modda çalışan private akışın gerçekten çerçeve teslim ettiğini ve kaydın içine
girdiğini kanıtlamak. Ayrı bir kurulum yok: emir gerçek testnet hesabına gider, akış da çalışan
`fbot-testnet` servisinin bağlantısıdır.

Güvenlik: emir piyasanın **%50 altında** bir LIMIT BUY'dır (dolması mümkün değil), miktarı en küçük
adımdır ve saniyeler içinde iptal edilir. Betik sonunda açık emir ve pozisyon sayısı doğrulanır;
sıfır değilse hata verir. Pozisyon açmaz, market emri göndermez.

Kullanım: PYTHONPATH=. python -m scripts.probe_userdata
"""
from __future__ import annotations

import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from fbot.core.rounding import fmt_price, fmt_qty, round_tick
from fbot.gateway.credfile import read_testnet_state, testnet_paths
from fbot.gateway.rest import exchange_info
from fbot.gateway.testnet import TestnetClient

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "BTCUSDT"


def filters_for(symbol: str):
    ex = exchange_info()
    s = next(x for x in ex["symbols"] if x["symbol"] == symbol)
    f = {x["filterType"]: x for x in s["filters"]}
    return (Decimal(f["LOT_SIZE"]["stepSize"]), Decimal(f["LOT_SIZE"]["minQty"]),
            Decimal(f["PRICE_FILTER"]["tickSize"]), Decimal(f["MIN_NOTIONAL"]["notional"]))


def main() -> None:
    state = read_testnet_state(testnet_paths(ROOT))
    if state.creds is None:
        raise SystemExit(f"testnet anahtarı yok: {state.reason}")
    c = TestnetClient(state.creds)
    now = lambda: int(time.time() * 1000)

    step, min_qty, tick, min_notional = filters_for(SYMBOL)
    book = c.signed("GET", "/fapi/v1/ticker/price", {"symbol": SYMBOL}, now())
    mark = Decimal(book["price"])
    price = round_tick(mark / 2, tick, "floor")                 # %50 altı: dolması mümkün değil
    qty = max(min_qty, (min_notional / price).quantize(step) + step)
    cid = f"probe{now()}"

    out = {"symbol": SYMBOL, "mark": str(mark), "limit_price": str(price), "qty": str(qty), "cid": cid}
    r = c.place_order({"symbol": SYMBOL, "side": "BUY", "type": "LIMIT", "timeInForce": "GTC",
                       "quantity": fmt_qty(qty, step), "price": fmt_price(price, tick),
                       "newClientOrderId": cid}, now())
    out["placed"] = {"orderId": r.get("orderId"), "status": r.get("status")}
    time.sleep(3)                                              # akışın çerçeveyi teslim etmesi için
    d = c.cancel_order({"symbol": SYMBOL, "origClientOrderId": cid}, now())
    out["canceled"] = {"orderId": d.get("orderId"), "status": d.get("status")}

    time.sleep(2)
    open_orders = [o for o in c.open_orders(now()) if o.get("symbol") == SYMBOL]
    positions = [p for p in c.positions(now()) if p.get("symbol") == SYMBOL and Decimal(str(p.get("positionAmt", 0))) != 0]
    out["temiz"] = {"open_orders": len(open_orders), "open_positions": len(positions)}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    if open_orders or positions:
        raise SystemExit("HESAP TEMİZ DEĞİL: açık emir ya da pozisyon kaldı")


if __name__ == "__main__":
    main()
    sys.exit(0)
