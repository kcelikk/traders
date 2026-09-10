"""Unit economics tablosu üretir. Girdi: data/unit-economics/ (funding, depth, exchangeInfo).
Kullanım: python -m scripts.unit_economics > docs/unit-economics.generated.md"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.unit_economics_core import breakeven_move_pct, breakeven_winrate, funding_stats, slippage_bps

D = Path("data/unit-economics")
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
NOTIONALS = [100, 500, 1_000, 5_000, 20_000]
# Komisyon oranları: RESMİ SAYFA LOGIN'SİZ RENDER ETMİYOR → üçüncü taraf, doğrulanmadı.
# Hesaptan GET /fapi/v1/commissionRate ile düzeltilecek (anahtar gerekir).
FEES = {"VIP0 (doğrulanmadı)": {"maker": 0.02, "taker": 0.05}}
BNB_DISCOUNT = 0.10  # resmi FAQ: "10% discount ... when they use BNB" (2026-05-01)
HOLD_HOURS = [5 / 60, 0.5, 2, 8, 24]
TARGET_MOVES = [0.3, 0.5, 1.0, 2.0]
RRS = [1.0, 1.5, 2.0]


def levels(side):
    return [(float(p), float(q)) for p, q in side]


def main():
    out = []
    # ---- funding
    out += ["## Funding (kaynak: GET /fapi/v1/fundingRate, son 500 kayıt; interval: GET /fapi/v1/fundingInfo)", "",
            "| Sembol | n | aralık (saat) | ort. imzalı (%/aralık) | ort. mutlak (%/aralık) | p95 mutlak | maks mutlak | ort. mutlak (%/saat) | kapsam |",
            "|---|---|---|---|---|---|---|---|---|"]
    fund = {}
    info = {x["symbol"]: x for x in json.load(open(D / "fundingInfo.json"))}
    for s in SYMBOLS:
        rows = json.load(open(D / f"funding_{s}.json"))
        ih = info.get(s, {}).get("fundingIntervalHours", 8)
        st = funding_stats([float(r["fundingRate"]) for r in rows], ih)
        fund[s] = st
        t0, t1 = rows[0]["fundingTime"], rows[-1]["fundingTime"]
        days = (t1 - t0) / 86400000
        out.append(f"| {s} | {st['n']} | {ih} | {st['mean_pct']:+.4f} | {st['mean_abs_pct']:.4f} | {st['p95_abs_pct']:.4f} | {st['max_abs_pct']:.4f} | {st['mean_abs_pct_per_hour']:.5f} | {days:.0f} gün |")

    # ---- slippage
    out += ["", "## Spread ve slippage (kaynak: GET /fapi/v1/depth limit=100, 3 anlık görüntü, 2 s arayla)", "",
            "| Sembol | best bid | best ask | spread (bps) | " + " | ".join(f"alış {n} USDT (bps)" for n in NOTIONALS) + " | " + " | ".join(f"satış {n} USDT (bps)" for n in NOTIONALS) + " |",
            "|---|---|---|---|" + "---|" * (2 * len(NOTIONALS))]
    slip = {}
    for s in SYMBOLS:
        snaps = [json.load(open(D / f"depth_{s}_{i}.json")) for i in (1, 2, 3)]
        buys, sells, spreads, bb, ba = {n: [] for n in NOTIONALS}, {n: [] for n in NOTIONALS}, [], [], []
        for sn in snaps:
            asks, bids = levels(sn["asks"]), levels(sn["bids"])
            best_ask, best_bid = asks[0][0], bids[0][0]
            bb.append(best_bid); ba.append(best_ask)
            spreads.append((best_ask - best_bid) / best_ask * 1e4)
            for n in NOTIONALS:
                b = slippage_bps(asks, n, best_ask, "buy")
                a = slippage_bps(bids, n, best_bid, "sell")
                if b is not None: buys[n].append(b)
                if a is not None: sells[n].append(a)
        avg = lambda xs: (sum(xs) / len(xs)) if xs else None
        slip[s] = {"spread": avg(spreads), "buy": {n: avg(buys[n]) for n in NOTIONALS}, "sell": {n: avg(sells[n]) for n in NOTIONALS}}
        f = lambda v: "—" if v is None else f"{v:.2f}"
        out.append(f"| {s} | {avg(bb):.2f} | {avg(ba):.2f} | {f(avg(spreads))} | " + " | ".join(f(slip[s]['buy'][n]) for n in NOTIONALS) + " | " + " | ".join(f(slip[s]['sell'][n]) for n in NOTIONALS) + " |")

    # ---- başabaş tablosu
    out += ["", "## Başabaş hareket (%) — gidiş-dönüş, notional yüzdesi", "",
            "Varsayımlar: slippage = 1.000 USDT defter yürüyüşü + yarım spread (market emri best'i geçer); funding = ort. mutlak oran × tutma süresi (aleyhte varsayım).", ""]
    for s in SYMBOLS:
        half_spread = slip[s]["spread"] / 2 / 100  # bps→% : /100
        sl_in = slip[s]["buy"][1000] / 100 + half_spread
        sl_out = slip[s]["sell"][1000] / 100 + half_spread
        fh = fund[s]["mean_abs_pct_per_hour"]
        out += [f"### {s}", "", "| Komisyon senaryosu | tutma | komisyon | slippage (giriş+çıkış) | funding | **başabaş hareket %** |", "|---|---|---|---|---|---|"]
        for name, fee in FEES.items():
            for bnb in (False, True):
                disc = (1 - BNB_DISCOUNT) if bnb else 1.0
                for combo, (fi, fo) in {"taker/taker": (fee["taker"], fee["taker"]), "maker/taker": (fee["maker"], fee["taker"]), "maker/maker": (fee["maker"], fee["maker"])}.items():
                    for h in HOLD_HOURS:
                        m = breakeven_move_pct(fi * disc, fo * disc, sl_in, sl_out, fh * h)
                        hold = f"{h*60:.0f} dk" if h < 1 else f"{h:.0f} sa"
                        out.append(f"| {name} {combo}{' +BNB' if bnb else ''} | {hold} | {(fi+fo)*disc:.3f} | {sl_in+sl_out:.3f} | {fh*h:.4f} | **{m:.3f}** |")
        out.append("")

    # ---- başabaş kazanma oranı
    out += ["## Başabaş kazanma oranı — BTCUSDT, taker/taker VIP0, 30 dk tutma, 1.000 USDT", ""]
    s = "BTCUSDT"
    half_spread = slip[s]["spread"] / 2 / 100
    cost = breakeven_move_pct(0.05, 0.05, slip[s]["buy"][1000] / 100 + half_spread, slip[s]["sell"][1000] / 100 + half_spread, fund[s]["mean_abs_pct_per_hour"] * 0.5)
    out += [f"Toplam maliyet: **{cost:.3f}%** notional", "", "| hedef hareket | " + " | ".join(f"R:R {r}" for r in RRS) + " |", "|---|" + "---|" * len(RRS)]
    for mv in TARGET_MOVES:
        cells = []
        for r in RRS:
            p = breakeven_winrate(r, mv, cost)
            cells.append("imkânsız" if p is None else f"{p*100:.1f}%")
        out.append(f"| {mv:.1f}% | " + " | ".join(cells) + " |")
    out += ["", "Maliyetsiz klasik başabaş (karşılaştırma): " + ", ".join(f"R:R {r} → {100/(1+r):.1f}%" for r in RRS)]
    print("\n".join(out))


if __name__ == "__main__":
    main()
