"""İleriye dönük net getiri örnekleri (ADR 0008 §5–7). Saf."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostScenario:
    name: str
    fee_in_pct: float
    fee_out_pct: float


def forward_samples(bars: list[dict], states: list[str], dirs: dict[int, list[tuple[str, str]]],
                    horizons: list[int], cost: CostScenario, bar_ms: int) -> list[dict]:
    """bars: tek sembol, zaman sıralı. dirs: bar indeksi → [(yön, etiket)].
    Giriş: bar i+1 open ± yarım spread(i). Çıkış: bar i+h close ∓ yarım spread(i+h). Örtüşmeyen: (state, dir, h) başına."""
    out = []
    n = len(bars)
    last_i: dict[tuple, int] = {}
    for i in range(n):
        st = states[i]
        if st == "S0" or i not in dirs:
            continue
        for h in horizons:
            j = i + h
            if j >= n:
                continue
            # ardışıklık: i..j arası boşluk yok
            if bars[j]["start_ms"] - bars[i]["start_ms"] != h * bar_ms:
                continue
            for d, tag in dirs[i]:
                key = (st, d, h)
                if key in last_i and i < last_i[key] + h:
                    continue
                hs_in = (bars[i]["spread_bps"] or 0.0) / 2 / 1e4
                hs_out = (bars[j]["spread_bps"] or 0.0) / 2 / 1e4
                if d == "long":
                    entry = bars[i + 1]["open"] * (1 + hs_in)
                    exit_ = bars[j]["close"] * (1 - hs_out)
                    gross = exit_ / entry - 1
                else:
                    entry = bars[i + 1]["open"] * (1 - hs_in)
                    exit_ = bars[j]["close"] * (1 + hs_out)
                    gross = 1 - exit_ / entry
                # funding: (giriş zamanı, çıkış zamanı] aralığında funding anı varsa
                t_in, t_out = bars[i + 1]["start_ms"], bars[j]["end_ms"]
                nf, fr = bars[i]["next_funding_ms"], bars[i]["funding_rate"]
                funding_pct = 0.0
                if nf is not None and fr is not None and t_in < nf <= t_out:
                    funding_pct = (fr if d == "long" else -fr) * 100   # long pozitif oranı öder
                cost_pct = cost.fee_in_pct + cost.fee_out_pct + funding_pct
                out.append({"i": i, "t_ms": bars[i]["end_ms"], "symbol": bars[i]["symbol"], "state": st, "dir": d, "tag": tag,
                            "h": h, "gross_pct": gross * 100, "funding_pct": funding_pct, "cost_pct": cost_pct,
                            "net_pct": gross * 100 - cost_pct})
                last_i[key] = i
    return out
