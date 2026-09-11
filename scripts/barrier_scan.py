"""Hücre + SL/TP taraması: hangi (durum, yön, stop, hedef) birleşimi maliyet üstü net üretiyor?

`allowed_cells` ve `sl_pct`/`tp_pct` ancak ölçümle doldurulur. Bu betik bars.jsonl üzerinde
durumları etiketler, her giriş için üçlü bariyeri (stop / hedef / süre) uygular ve maliyet
düşülmüş net beklentiyi bootstrap güven aralığıyla raporlar.

Zaman bazlı keşif/doğrulama ayrımı ADR 0008 ile aynıdır: ilk %70 keşif, son %30 doğrulama.
Bir birleşimin "geçti" sayılması için **her ikisinde de** güven aralığının alt sınırı sıfırın
üstünde olmalıdır. Bu eşiği gevşetmek sonuç aramaktır.

Kullanım:
  python -m scripts.barrier_scan data/research/<run>/bars.jsonl [--json-out out.json] [--top 20]
"""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

from fbot.research.barrier import BarrierConfig, evaluate
from fbot.research.features import FeatureConfig, compute_features
from fbot.research.states import StateConfig, label_state
from fbot.research.stats import bootstrap_ci_fast as bootstrap_ci

SL_GRID = [0.3, 0.5, 0.8, 1.2]
TP_GRID = [0.3, 0.6, 1.0, 1.6, 2.4]
HOLD_GRID = [15, 60]          # bar = dakika
STATES = ("S1", "S2", "S3", "S4")
DIRS = ("long", "short")


def load_bars(path: Path) -> dict[str, list]:
    by: dict[str, list] = defaultdict(list)
    for line in Path(path).open():
        b = json.loads(line)
        by[b["symbol"]].append(b)
    for rows in by.values():
        rows.sort(key=lambda r: r["start_ms"])
    return dict(by)


def label_all(by_symbol: dict, fcfg: FeatureConfig, scfg: StateConfig) -> dict[str, list]:
    """Her bara durum etiketi. Look-ahead yok: etiket yalnızca o barda ve öncesinde bilinenle hesaplanır."""
    out = {}
    for sym, rows in by_symbol.items():
        feats = compute_features(rows, fcfg)
        out[sym] = [label_state(f, scfg) for f in feats]
    return out


def spread_cost(rows: list, default_bps: float = 1.0) -> float:
    """Gidiş-dönüş spread maliyeti (%): barlardaki ölçülmüş spread medyanı; yoksa varsayılan."""
    vals = sorted(r["spread_bps"] for r in rows if r.get("spread_bps") is not None)
    bps = vals[len(vals) // 2] if vals else default_bps
    return bps / 100.0          # tek yön; giriş taker, çıkış taker → iki kez sayılır aşağıda


def scan(by_symbol: dict, labels: dict, fee_in: float, fee_out: float, disc_frac: float,
         n_boot: int, seed: int, alpha: float, min_n: int, stride: int = 1, screen_boot: int = 300) -> list[dict]:
    """İki aşamalı: tüm birleşimler ucuz bootstrap ile elenir (`screen_boot`), ayakta kalanlar ve
    en iyi 10 birleşim config'deki tam `n_boot` ile yeniden ölçülür. Eşik gevşetilmez; kararı
    her zaman tam ölçüm verir, ucuz aşama yalnızca hangi birleşimlere bakılacağını seçer."""
    # Sembol başına sabitler bir kez hesaplanır (maliyet, kesim noktası, giriş indeksleri)
    costs, cuts, entries = {}, {}, {}
    for sym, rows in by_symbol.items():
        costs[sym] = fee_in + fee_out + 2 * spread_cost(rows)
        cuts[sym] = int(len(rows) * disc_frac)
        for state in STATES:
            idx = [i for i, st in enumerate(labels[sym]) if st == state and i + 1 < len(rows)]
            entries[(sym, state)] = idx[::stride]
    results = []
    for state in STATES:
        for direction in DIRS:
            for hold in HOLD_GRID:
                for sl in SL_GRID:
                    for tp in TP_GRID:
                        disc, val = [], []
                        for sym, rows in by_symbol.items():
                            cut = cuts[sym]
                            cfg = BarrierConfig(sl_pct=sl, tp_pct=tp, max_hold=hold, cost_pct=costs[sym])
                            for i in entries[(sym, state)]:
                                r = evaluate(rows[i]["close"], direction, rows[i + 1: i + 1 + hold], cfg)
                                if r is None:
                                    continue
                                (disc if i < cut else val).append(r["net_pct"])
                        if len(disc) < min_n or len(val) < min_n:
                            continue
                        d_lo, _ = bootstrap_ci(disc, screen_boot, seed, alpha)
                        v_lo, v_hi = bootstrap_ci(val, screen_boot, seed, alpha)
                        results.append({
                            "state": state, "dir": direction, "hold": hold, "sl": sl, "tp": tp,
                            "n_disc": len(disc), "disc_mean": sum(disc) / len(disc), "disc_lo": d_lo,
                            "n_val": len(val), "val_mean": sum(val) / len(val), "val_lo": v_lo, "val_hi": v_hi,
                            "gecti": bool(d_lo > 0 and v_lo > 0), "boot": screen_boot,
                            "_disc": disc, "_val": val,
                        })
    results.sort(key=lambda r: -r["val_mean"])
    for r in results[:10] + [x for x in results if x["gecti"]]:
        if r["boot"] == n_boot:
            continue
        r["disc_lo"], _ = bootstrap_ci(r["_disc"], n_boot, seed, alpha)
        r["val_lo"], r["val_hi"] = bootstrap_ci(r["_val"], n_boot, seed, alpha)
        r["gecti"] = bool(r["disc_lo"] > 0 and r["val_lo"] > 0)
        r["boot"] = n_boot
    for r in results:
        r.pop("_disc", None)
        r.pop("_val", None)
    return sorted(results, key=lambda r: -r["val_mean"])


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("bars")
    ap.add_argument("--config", default="config/research.toml")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--scenario", default="taker/taker")
    ap.add_argument("--stride", type=int, default=1, help="giriş örnekleme adımı (hız için; yanlılık üretmez)")
    ap.add_argument("--screen-boot", type=int, default=300, help="eleme bootstrap sayısı; finalistler tam sayıyla ölçülür")
    a = ap.parse_args(argv)
    cfg = tomllib.loads(Path(a.config).read_text())
    f, st, bs, sm = cfg["features"], cfg["states"], cfg["bootstrap"], cfg["sampling"]
    sc = next(x for x in cfg["costs"]["scenarios"] if x["name"] == a.scenario)

    by = load_bars(Path(a.bars))
    fcfg = FeatureConfig(W=f["W"], N_short=f["N_short"], N_long=f["N_long"])
    labels = label_all(by, fcfg, StateConfig(st["p_lo"], st["p_hi"]))
    rows = scan(by, labels, sc["fee_in_pct"], sc["fee_out_pct"], sm["discovery_frac"],
                bs["n_boot"], bs["seed"], bs["alpha"], sm["min_n"], stride=a.stride, screen_boot=a.screen_boot)
    passed = [r for r in rows if r["gecti"]]
    out = {"bars": sum(len(v) for v in by.values()), "symbols": len(by), "scenario": a.scenario,
           "combinations": len(rows), "passed": len(passed), "rows": rows}
    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(json.dumps(out, indent=1))
    print(f"# Bariyer taraması · {a.scenario} · {out['bars']} bar · {out['symbols']} sembol")
    print(f"# {len(rows)} birleşim değerlendirildi · **geçen: {len(passed)}**")
    print(f"\n{'durum':6s} {'yön':6s} {'tut':>4s} {'sl%':>5s} {'tp%':>5s} {'n_dog':>7s} {'keşif_net':>10s} {'dog_net':>9s} {'CI alt':>9s} {'CI üst':>9s}  karar")
    for r in rows[: a.top]:
        print(f"{r['state']:6s} {r['dir']:6s} {r['hold']:4d} {r['sl']:5.2f} {r['tp']:5.2f} {r['n_val']:7d} "
              f"{r['disc_mean']:10.4f} {r['val_mean']:9.4f} {r['val_lo']:9.4f} {r['val_hi']:9.4f}  {'GEÇTİ' if r['gecti'] else '—'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
