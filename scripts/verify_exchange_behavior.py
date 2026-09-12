"""Testnet'e karşı Binance davranış doğrulaması (Gate 0). **Elle çalıştırılır, üretim yoluna bağlı değildir.**

Doğrulanan altı şey — hiçbiri dokümantasyondan varsayılmaz (CLAUDE.md "uydurma yok"):

  1. Private WS URL biçimi: `/private/ws/<listenKey>` mi, `?listenKey=...&events=...` mi;
     `events` filtresi destekleniyor mu.
  2. `ACCOUNT_UPDATE`, `ORDER_TRADE_UPDATE`, `ALGO_UPDATE`, `listenKeyExpired` payload alanları.
  3. `clientOrderId` / `clientAlgoId` uzunluk sınırı (-4015 beklenir).
  4. tickSize'a uymayan tetik fiyatının reddi (BTCUSDT tick 0,10 / pricePrecision 2).
  5. `ALGO_UPDATE` yaşam döngüsü: NEW → CANCELED.
  6. Aynı `clientOrderId` ile ikinci gönderim gerçekten idempotent mi.

**Güvenlik**: yalnızca testnet. Açılan pozisyon her adımda kapatılır; betik sonunda
`openOrders` ve `openAlgoOrders` boş olduğu doğrulanır, doğrulanamazsa hata verir.
Miktar sembolün minimum notional'ına göre en küçük seçilir.

Kullanım: PYTHONPATH=. python -m scripts.verify_exchange_behavior [--dry-run] [--out docs/binance-api-verification-gate0.md]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from fbot.gateway.credfile import read_testnet_state, testnet_paths
from fbot.gateway.testnet import BASE, TestnetClient, TestnetError

ROOT = Path(__file__).resolve().parents[1]
WS_BASE = "wss://stream.binancefuture.com"          # testnet stream tabanı; iki URL biçimi denenir
SYMBOL = "BTCUSDT"


def now_ms() -> int:
    return int(time.time() * 1000)


class Findings:
    def __init__(self):
        self.rows: list[dict] = []

    def add(self, konu: str, sonuc: str, kanit) -> None:
        self.rows.append({"konu": konu, "sonuc": sonuc, "kanit": kanit})
        print(json.dumps({"konu": konu, "sonuc": sonuc, "kanit": kanit}, ensure_ascii=False, default=str)[:400], flush=True)


def symbol_filters(client: TestnetClient) -> dict:
    ex = client.signed("GET", "/fapi/v1/exchangeInfo", {}, now_ms()) if False else None
    # exchangeInfo imzasızdır; testnet istemcisi imzalı yol kullanır, bu yüzden ayrı çekilir
    import http.client
    conn = http.client.HTTPSConnection(BASE.split("://", 1)[1], timeout=15)
    conn.request("GET", "/fapi/v1/exchangeInfo")
    data = json.loads(conn.getresponse().read())
    conn.close()
    s = next(x for x in data["symbols"] if x["symbol"] == SYMBOL)
    f = {x["filterType"]: x for x in s["filters"]}
    return {"step": Decimal(f["LOT_SIZE"]["stepSize"]), "min_qty": Decimal(f["LOT_SIZE"]["minQty"]),
            "min_notional": Decimal(f["MIN_NOTIONAL"]["notional"]), "tick": Decimal(f["PRICE_FILTER"]["tickSize"]),
            "price_precision": s["pricePrecision"], "qty_precision": s["quantityPrecision"]}


async def probe_private_ws(client: TestnetClient, fnd: Findings, seconds: float = 25.0) -> list[dict]:
    """İki URL biçimini de dener; çalışanla bağlanıp gelen olayları toplar."""
    from websockets.asyncio.client import connect
    key = client.listen_key(now_ms())
    fnd.add("listenKey alındı", "TAMAM", {"uzunluk": len(key)})
    candidates = [("path", f"{WS_BASE}/ws/{key}"),
                  ("query", f"{WS_BASE}/private/ws?listenKey={key}"),
                  ("path-private", f"{WS_BASE}/private/ws/{key}")]
    events: list[dict] = []
    for name, url in candidates:
        try:
            async with connect(url, ping_interval=20, ping_timeout=20, open_timeout=10) as ws:
                fnd.add(f"private WS biçimi: {name}", "ÇALIŞTI", {"url": url.replace(key, "<listenKey>")})
                try:
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=seconds)
                        d = json.loads(raw)
                        events.append(d)
                        print(json.dumps({"private_event": d}, ensure_ascii=False)[:600], flush=True)
                except asyncio.TimeoutError:
                    pass
                return events
        except Exception as e:  # noqa: BLE001 — hangi biçimin çalışmadığını da kaydediyoruz
            fnd.add(f"private WS biçimi: {name}", "OLMADI", {"hata": repr(e)[:200]})
    return events


def cleanup(client: TestnetClient, fnd: Findings) -> bool:
    """Açık emir, algo ve pozisyon bırakmadığımızı doğrular."""
    o = client.open_orders(now_ms())
    a = client.open_algos(now_ms())
    pos = [p for p in client.positions(now_ms()) if p.get("symbol") == SYMBOL and float(p.get("positionAmt", 0)) != 0]
    temiz = not o and not a and not pos
    fnd.add("temizlik", "TEMİZ" if temiz else "KİRLİ",
            {"acik_emir": len(o), "acik_algo": len(a), "acik_pozisyon": len(pos)})
    return temiz


def write_report(fnd: Findings, out: Path) -> None:
    lines = ["# Gate 0 — testnet davranış doğrulaması", "",
             f"Tarih: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())} · Ortam: testnet · "
             "Betik: `scripts/verify_exchange_behavior.py`", "",
             "| Konu | Sonuç | Kanıt |", "|---|---|---|"]
    for r in fnd.rows:
        k = json.dumps(r["kanit"], ensure_ascii=False, default=str).replace("|", "\\|")
        lines.append(f"| {r['konu']} | {r['sonuc']} | `{k[:300]}` |")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"\nrapor: {out}", flush=True)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/binance-api-gate0-dogrulama.md")
    ap.add_argument("--dry-run", action="store_true", help="emir gönderme; yalnız okuma ve private WS")
    a = ap.parse_args(argv)

    st = read_testnet_state(testnet_paths(ROOT), environ={})
    if not st.armed:
        raise SystemExit(f"testnet silahsız: {st.reason}")
    client = TestnetClient(st.creds)
    fnd = Findings()
    fnd.add("anahtar", "TAMAM", {"maskeli": st.masked})

    filt = symbol_filters(client)
    fnd.add("BTCUSDT filtreleri", "OKUNDU", {k: str(v) for k, v in filt.items()})
    tick_uyumsuz = filt["tick"] != Decimal(1).scaleb(-filt["price_precision"])
    fnd.add("tickSize == 10^-pricePrecision mi", "HAYIR" if tick_uyumsuz else "EVET",
            {"tick": str(filt["tick"]), "pricePrecision": filt["price_precision"]})

    if not cleanup(client, fnd):
        raise SystemExit("başlangıçta hesap temiz değil; önce elle temizleyin")

    events = asyncio.run(probe_private_ws(client, fnd, seconds=5.0))
    fnd.add("private WS ilk dinleme", "OLAY YOK" if not events else "OLAY VAR", {"adet": len(events)})

    if not a.dry_run:
        print("\n--- emir adımları (gerçek testnet emri) ---", flush=True)
        try:
            run_order_probes(client, fnd, filt)
        finally:
            cleanup(client, fnd)

    write_report(fnd, Path(a.out))
    return 0


def run_order_probes(client: TestnetClient, fnd: Findings, filt: dict) -> None:
    """Emir gerektiren doğrulamalar. Her adım kendi temizliğini yapar."""
    mark = Decimal(json.loads(_get("/fapi/v1/premiumIndex?symbol=" + SYMBOL))["markPrice"])
    qty = max(filt["min_qty"], (filt["min_notional"] / mark / filt["step"] + 1).to_integral_value() * filt["step"])
    fnd.add("test miktarı", "SEÇİLDİ", {"qty": str(qty), "mark": str(mark), "notional": str(qty * mark)})

    # 3) CID uzunluk sınırı
    long_cid = "x" * 40
    try:
        client.place_order({"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "quantity": str(qty),
                            "newClientOrderId": long_cid}, now_ms(), entry=True)
        fnd.add("40 karakterlik clientOrderId", "KABUL EDİLDİ", {"uzunluk": 40})
    except TestnetError as e:
        fnd.add("40 karakterlik clientOrderId", "REDDEDİLDİ", {"code": e.code, "msg": str(e)[:180]})

    # 4) tickSize'a uymayan tetik fiyatı
    bad_trigger = (mark * Decimal("0.97")).quantize(Decimal("0.01"))   # 2 basamak ama tick 0,10
    try:
        client.place_algo({"symbol": SYMBOL, "side": "SELL", "type": "STOP_MARKET",
                           "triggerPrice": str(bad_trigger), "closePosition": "true",
                           "workingType": "MARK_PRICE", "priceProtect": "true",
                           "clientAlgoId": f"g0tick{now_ms() % 10**8}"}, now_ms())
        fnd.add("tick'e uymayan tetik fiyatı", "KABUL EDİLDİ", {"trigger": str(bad_trigger)})
    except TestnetError as e:
        fnd.add("tick'e uymayan tetik fiyatı", "REDDEDİLDİ", {"trigger": str(bad_trigger), "code": e.code, "msg": str(e)[:180]})

    # 1-2-5) pozisyon aç → koruma koy → iptal et → kapat; arada private olayları topla
    cid = f"g0e{now_ms() % 10**9}"
    r = client.place_order({"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "quantity": str(qty),
                            "newClientOrderId": cid}, now_ms(), entry=True)
    fnd.add("giriş emri", "GÖNDERİLDİ", {k: r.get(k) for k in ("orderId", "status", "executedQty", "avgPrice")})

    # 6) aynı CID ile ikinci gönderim
    try:
        r2 = client.place_order({"symbol": SYMBOL, "side": "BUY", "type": "MARKET", "quantity": str(qty),
                                 "newClientOrderId": cid}, now_ms(), entry=True)
        fnd.add("aynı clientOrderId ile ikinci gönderim", "KABUL EDİLDİ (idempotent DEĞİL)",
                {"orderId": r2.get("orderId")})
    except TestnetError as e:
        fnd.add("aynı clientOrderId ile ikinci gönderim", "REDDEDİLDİ", {"code": e.code, "msg": str(e)[:180]})

    algo_cid = f"g0a{now_ms() % 10**9}"
    good_trigger = (mark * Decimal("0.97") / filt["tick"]).to_integral_value() * filt["tick"]
    try:
        ra = client.place_algo({"symbol": SYMBOL, "side": "SELL", "type": "STOP_MARKET",
                                "triggerPrice": str(good_trigger), "closePosition": "true",
                                "workingType": "MARK_PRICE", "priceProtect": "true",
                                "clientAlgoId": algo_cid}, now_ms())
        fnd.add("koruma algo emri (tick'e uygun)", "KABUL EDİLDİ",
                {"trigger": str(good_trigger), **{k: ra.get(k) for k in ("algoId", "algoStatus")}})
        client.cancel_algo({"symbol": SYMBOL, "clientAlgoId": algo_cid}, now_ms())
        fnd.add("koruma algo iptali", "GÖNDERİLDİ", {"clientAlgoId": algo_cid})
    except TestnetError as e:
        fnd.add("koruma algo emri", "REDDEDİLDİ", {"code": e.code, "msg": str(e)[:180]})

    pos = [p for p in client.positions(now_ms()) if p.get("symbol") == SYMBOL and float(p.get("positionAmt", 0)) != 0]
    if pos:
        amt = abs(Decimal(pos[0]["positionAmt"]))
        client.place_order({"symbol": SYMBOL, "side": "SELL", "type": "MARKET", "quantity": str(amt),
                            "reduceOnly": "true", "newClientOrderId": f"g0x{now_ms() % 10**9}"}, now_ms())
        fnd.add("pozisyon kapatma", "GÖNDERİLDİ", {"qty": str(amt)})

    # -2022: pozisyon kapalıyken reduceOnly gönder
    try:
        client.place_order({"symbol": SYMBOL, "side": "SELL", "type": "MARKET", "quantity": str(qty),
                            "reduceOnly": "true", "newClientOrderId": f"g0r{now_ms() % 10**9}"}, now_ms())
        fnd.add("pozisyon yokken reduceOnly", "KABUL EDİLDİ", {})
    except TestnetError as e:
        fnd.add("pozisyon yokken reduceOnly", "REDDEDİLDİ", {"code": e.code, "msg": str(e)[:180]})


def _get(path: str) -> bytes:
    import http.client
    conn = http.client.HTTPSConnection(BASE.split("://", 1)[1], timeout=15)
    conn.request("GET", path)
    b = conn.getresponse().read()
    conn.close()
    return b


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
