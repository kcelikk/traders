"""`-4130` ölçümü: aynı yönde ikinci koruma emri gerçekten konamıyor mu, seçenekler ne veriyor?

Gate 0 §7 bulgusu: pozisyon açıkken ikinci `STOP_MARKET closePosition=true` emri
`-4130` ile reddediliyor ("An open stop or take profit order with GTE and closePosition in the
direction is existing"). R3 kâr kilidi kuralı **önce yeni SL, sonra eskisinin iptali** sırasını
üretiyor; gerçek borsada bu, pozisyonu korumasız bırakır.

Bu betik üç seçeneği **ölçer**, varsaymaz:

  A) Bugünkü sıra (yeni → iptal): ikinci `closePosition` emri reddediliyor mu?
  B) `closePosition=false` + açık miktar: aynı yönde **birden çok** stop kabul ediliyor mu?
  C) Ters sıra (iptal → yeni): korumasız pencere ne kadar sürüyor?

**Güvenlik**: yalnız testnet. En küçük miktarla tek pozisyon açılır, ölçüm biter bitmez kapatılır.
`finally` bloğunda tüm algo'lar iptal edilir, pozisyon kapatılır ve sonunda açık emir/algo/pozisyon
sayısının **sıfır** olduğu doğrulanır; doğrulanamazsa betik hata verir.

Kullanım: PYTHONPATH=. python -m scripts.measure_4130 [--out docs/measure-4130.json]
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from fbot.core.rounding import fmt_price, fmt_qty, round_tick
from fbot.gateway.credfile import read_testnet_state, testnet_paths
from fbot.gateway.rest import exchange_info
from fbot.gateway.testnet import TestnetClient, TestnetError

ROOT = Path(__file__).resolve().parents[1]
SYMBOL = "BTCUSDT"


def now_ms() -> int:
    return int(time.time() * 1000)


class Log:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, adim: str, sonuc: str, kanit=None) -> dict:
        row = {"adim": adim, "sonuc": sonuc, "kanit": kanit}
        self.rows.append(row)
        print(json.dumps(row, ensure_ascii=False, default=str)[:400], flush=True)
        return row


def filters():
    s = next(x for x in exchange_info()["symbols"] if x["symbol"] == SYMBOL)
    f = {x["filterType"]: x for x in s["filters"]}
    return (Decimal(f["LOT_SIZE"]["stepSize"]), Decimal(f["LOT_SIZE"]["minQty"]),
            Decimal(f["PRICE_FILTER"]["tickSize"]), Decimal(f["MIN_NOTIONAL"]["notional"]))


def try_algo(c: TestnetClient, log: Log, adim: str, params: dict) -> dict:
    t0 = time.perf_counter()
    try:
        r = c.place_algo(params, now_ms())
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return log.add(adim, "KABUL", {"algoId": r.get("algoId"), "status": r.get("algoStatus"), "rtt_ms": ms})
    except TestnetError as e:
        ms = round((time.perf_counter() - t0) * 1000, 1)
        return log.add(adim, "RET", {"code": e.code, "msg": str(e)[:160], "rtt_ms": ms})


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    st = read_testnet_state(testnet_paths(ROOT))
    if st.creds is None:
        raise SystemExit(f"testnet anahtarı yok: {st.reason}")
    c = TestnetClient(st.creds, recv_window=10_000)   # ilk koşuda 5000 ms ile -1021 alındı
    log = Log()
    step, min_qty, tick, min_notional = filters()
    price = Decimal(c.signed("GET", "/fapi/v1/ticker/price", {"symbol": SYMBOL}, now_ms())["price"])
    qty = max(min_qty, (min_notional / price).quantize(step) + step)
    sl1 = round_tick(price * Decimal("0.90"), tick, "floor")     # long stop: piyasanın altında
    sl2 = round_tick(price * Decimal("0.92"), tick, "floor")     # daha sıkı ikinci stop
    log.add("baslangic", "TAMAM", {"price": str(price), "qty": str(qty), "sl1": str(sl1), "sl2": str(sl2)})

    base = {"symbol": SYMBOL, "side": "SELL", "positionSide": "BOTH", "workingType": "MARK_PRICE",
            "priceProtect": "true"}
    opened = False
    try:
        c.place_order({"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "positionSide": "BOTH",
                       "quantity": fmt_qty(qty, step), "newClientOrderId": f"m4130e{now_ms()}"}, now_ms())
        opened = True
        log.add("pozisyon açıldı", "TAMAM", {"qty": str(qty)})

        # --- A) bugünkü sıra: iki closePosition stop yan yana durabiliyor mu
        a1 = try_algo(c, log, "A1 ilk closePosition stop", {**base, "type": "STOP_MARKET",
                      "triggerPrice": fmt_price(sl1, tick), "closePosition": "true",
                      "clientAlgoId": f"m4130a1{now_ms()}"})
        a2 = try_algo(c, log, "A2 ikinci closePosition stop (eskisi dururken)", {**base, "type": "STOP_MARKET",
                      "triggerPrice": fmt_price(sl2, tick), "closePosition": "true",
                      "clientAlgoId": f"m4130a2{now_ms()}"})
        a3 = try_algo(c, log, "A3 take profit (stop dururken)", {**base, "type": "TAKE_PROFIT_MARKET",
                      "triggerPrice": fmt_price(round_tick(price * Decimal("1.10"), tick, "ceil"), tick),
                      "closePosition": "true", "clientAlgoId": f"m4130a3{now_ms()}"})

        # --- C) ters sıra: iptal → yeni. Korumasız pencere ölçülür.
        algos = [x for x in c.open_algos(now_ms()) if x.get("symbol") == SYMBOL]
        stop_id = next((x["clientAlgoId"] for x in algos if x.get("orderType", x.get("type")) == "STOP_MARKET"
                        or "a1" in str(x.get("clientAlgoId"))), None)
        window_ms = None
        if stop_id:
            t0 = time.perf_counter()
            c.cancel_algo({"symbol": SYMBOL, "clientAlgoId": stop_id}, now_ms())
            c1 = try_algo(c, log, "C yeni stop (iptalden sonra)", {**base, "type": "STOP_MARKET",
                          "triggerPrice": fmt_price(sl2, tick), "closePosition": "true",
                          "clientAlgoId": f"m4130c{now_ms()}"})
            window_ms = round((time.perf_counter() - t0) * 1000, 1)
            log.add("C korumasız pencere", "ÖLÇÜLDÜ", {"ms": window_ms, "yeni_stop": c1["sonuc"]})

        # --- B) closePosition=false + miktar: birden çok stop yan yana durabiliyor mu
        for x in c.open_algos(now_ms()):
            if x.get("symbol") == SYMBOL:
                c.cancel_algo({"symbol": SYMBOL, "clientAlgoId": x["clientAlgoId"]}, now_ms())
        log.add("algolar temizlendi", "TAMAM", {"kalan": len([x for x in c.open_algos(now_ms()) if x.get("symbol") == SYMBOL])})
        b1 = try_algo(c, log, "B1 closePosition=false + miktar", {**base, "type": "STOP_MARKET",
                      "triggerPrice": fmt_price(sl1, tick), "closePosition": "false",
                      "quantity": fmt_qty(qty, step), "reduceOnly": "true",
                      "clientAlgoId": f"m4130b1{now_ms()}"})
        b2 = try_algo(c, log, "B2 ikinci closePosition=false stop", {**base, "type": "STOP_MARKET",
                      "triggerPrice": fmt_price(sl2, tick), "closePosition": "false",
                      "quantity": fmt_qty(qty, step), "reduceOnly": "true",
                      "clientAlgoId": f"m4130b2{now_ms()}"})
        # --- D) karışık tip: closePosition=true stop dururken miktar tabanlı stop konabiliyor mu?
        # Kararı bu belirliyor: R3 yer değiştirmesi "önce yeni, sonra iptal" sırasını koruyabilir mi.
        for x in c.open_algos(now_ms()):
            if x.get("symbol") == SYMBOL:
                c.cancel_algo({"symbol": SYMBOL, "clientAlgoId": x["clientAlgoId"]}, now_ms())
        d1 = try_algo(c, log, "D1 closePosition=true stop", {**base, "type": "STOP_MARKET",
                      "triggerPrice": fmt_price(sl1, tick), "closePosition": "true",
                      "clientAlgoId": f"m4130d1{now_ms()}"})
        d2 = try_algo(c, log, "D2 miktar tabanlı stop (closePosition stop dururken)", {**base, "type": "STOP_MARKET",
                      "triggerPrice": fmt_price(sl2, tick), "closePosition": "false",
                      "quantity": fmt_qty(qty, step), "reduceOnly": "true",
                      "clientAlgoId": f"m4130d2{now_ms()}"})
        sonuc = {"A_ikinci_closePosition": a2["sonuc"], "A_take_profit_yanyana": a3["sonuc"],
                 "B_closePosition_false_ilk": b1["sonuc"], "B_closePosition_false_ikinci": b2["sonuc"],
                 "C_korumasiz_pencere_ms": window_ms,
                 "D_karisik_tip_yanyana": d2["sonuc"], "D_closePosition_ilk": d1["sonuc"]}
    finally:
        # --- temizlik: her hâlükârda
        for x in c.open_algos(now_ms()):
            if x.get("symbol") == SYMBOL:
                try:
                    c.cancel_algo({"symbol": SYMBOL, "clientAlgoId": x["clientAlgoId"]}, now_ms())
                except TestnetError as e:
                    log.add("temizlik algo iptali", "HATA", {"code": e.code})
        if opened:
            # Kapatma tek denemeye bırakılmaz: ilk koşuda -1021 (recvWindow) alındı ve pozisyon
            # açık kaldı. Her deneme **taze damga** alır.
            for deneme in range(3):
                pos = next((p for p in c.positions(now_ms()) if p.get("symbol") == SYMBOL), None)
                amt = Decimal(str((pos or {}).get("positionAmt", "0")))
                if amt == 0:
                    break
                try:
                    c.place_order({"symbol": SYMBOL, "side": "SELL" if amt > 0 else "BUY", "type": "MARKET",
                                   "positionSide": "BOTH", "quantity": fmt_qty(abs(amt), step),
                                   "reduceOnly": "true", "newClientOrderId": f"m4130x{now_ms()}"}, now_ms())
                    break
                except TestnetError as e:
                    log.add(f"kapatma denemesi {deneme + 1}", "HATA", {"code": e.code, "msg": str(e)[:120]})
                    time.sleep(1)
        time.sleep(1)
        left = {"algos": len([x for x in c.open_algos(now_ms()) if x.get("symbol") == SYMBOL]),
                "orders": len([x for x in c.open_orders(now_ms()) if x.get("symbol") == SYMBOL]),
                "positions": len([p for p in c.positions(now_ms())
                                  if p.get("symbol") == SYMBOL and Decimal(str(p.get("positionAmt", "0"))) != 0])}
        log.add("temizlik", "TAMAM" if not any(left.values()) else "KİRLİ", left)

    out = {"symbol": SYMBOL, "sonuc": sonuc, "temiz": left, "adimlar": log.rows}
    text = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text + "\n")      # kirli kalsa bile kanıt yazılır
    print(text)
    if any(left.values()):
        raise SystemExit("HESAP TEMİZ DEĞİL: elle temizle")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
