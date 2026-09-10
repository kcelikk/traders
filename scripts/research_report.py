"""Faz 3 raporu: bars.jsonl + config/research.toml → Markdown (stdout). Deterministik (seed'li bootstrap).
Kullanım: python -m scripts.research_report data/research/<run>/bars.jsonl [--config config/research.toml]"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from fbot.research.features import FeatureConfig, compute_features
from fbot.research.forward import CostScenario, forward_samples
from fbot.research.states import STATES, StateConfig, directions, label_state
from fbot.research.stats import bootstrap_ci, summarize


def fmt(v, nd=3):
    return "—" if v is None or v != v else f"{v:.{nd}f}"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("bars")
    ap.add_argument("--config", default="config/research.toml")
    ap.add_argument("--json-out", default=None, help="hücre tablosunu JSON olarak da yaz (UI için)")
    a = ap.parse_args(argv)
    jcells = []
    cfg_bytes = Path(a.config).read_bytes()
    cfg = tomllib.loads(cfg_bytes.decode())
    cfg_hash = hashlib.sha256(cfg_bytes).hexdigest()[:12]
    fcfg = FeatureConfig(**cfg["features"])
    scfg = StateConfig(**cfg["states"])
    horizons = cfg["horizons"]["minutes"]
    bar_ms = cfg["bars"]["bar_ms"]
    scenarios = [CostScenario(**s) for s in cfg["costs"]["scenarios"]]
    disc = cfg["sampling"]["discovery_frac"]
    min_n = cfg["sampling"]["min_n"]
    bs = cfg["bootstrap"]

    by_sym = defaultdict(list)
    for line in Path(a.bars).read_text().splitlines():
        if line.strip():
            b = json.loads(line)
            by_sym[b["symbol"]].append(b)
    all_t = sorted(b["end_ms"] for bars in by_sym.values() for b in bars)
    if not all_t:
        print("bar yok"); return
    split_ms = all_t[int(len(all_t) * disc)] if len(all_t) > 1 else all_t[-1]
    hours = (all_t[-1] - all_t[0]) / 3.6e6

    state_counts = Counter()
    transitions = Counter()
    sym_state = defaultdict(Counter)
    samples = {sc.name: [] for sc in scenarios}
    for sym, bars in by_sym.items():
        bars.sort(key=lambda b: b["start_ms"])
        feats = compute_features(bars, fcfg)
        states = [label_state(f, scfg) for f in feats]
        for i, s in enumerate(states):
            state_counts[s] += 1
            sym_state[sym][s] += 1
            if i:
                transitions[(states[i - 1], s)] += 1
        dirs = {i: directions(s, feats[i]) for i, s in enumerate(states) if s != "S0"}
        for sc in scenarios:
            samples[sc.name] += forward_samples(bars, states, dirs, horizons, sc, bar_ms)

    out = [f"# Faz 3 araştırma raporu — `{Path(a.bars).parent.name}`", "",
           f"Kapsam: {hours:.1f} saat, {len(by_sym)} sembol, {sum(len(v) for v in by_sym.values())} bar. Config `{cfg_hash}` (W={fcfg.W}, N={fcfg.N_short}/{fcfg.N_long}, p={scfg.p_lo}/{scfg.p_hi}). Keşif/doğrulama ayrımı: {split_ms} ms epoch (%{disc*100:.0f}). Bootstrap n={bs['n_boot']}, seed={bs['seed']}.", "",
           "## Durum dağılımı", "", "| Durum | bar | oran |", "|---|---|---|"]
    tot = sum(state_counts.values())
    for s in STATES:
        out.append(f"| {s} | {state_counts[s]} | {state_counts[s] / tot * 100:.1f}% |")
    out += ["", "## Geçiş matrisi (satır → sütun)", "", "| | " + " | ".join(STATES) + " |", "|---|" + "---|" * len(STATES)]
    for s in STATES:
        out.append(f"| {s} | " + " | ".join(str(transitions[(s, t)]) for t in STATES) + " |")

    decision_cells = []
    for sc in scenarios:
        out += ["", f"## Hücreler — maliyet senaryosu **{sc.name}** (giriş {sc.fee_in_pct}% + çıkış {sc.fee_out_pct}% + spread + funding)", "",
                "| durum | etiket | yön | ufuk | bölüm | n | brüt % | maliyet % | **net %** | medyan | kazanma | CI alt | CI üst | karar |",
                "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        cells = defaultdict(lambda: {"disc": [], "val": []})
        for x in samples[sc.name]:
            part = "disc" if x["t_ms"] < split_ms else "val"
            cells[(x["state"], x["tag"], x["dir"], x["h"])][part].append(x)
        for key in sorted(cells):
            st, tag, d, h = key
            disc_ok = None
            for part in ("disc", "val"):
                xs = cells[key][part]
                nets = [x["net_pct"] for x in xs]
                s = summarize(nets)
                lo, hi = bootstrap_ci(nets, bs["n_boot"], bs["seed"], bs["alpha"]) if nets else (float("nan"), float("nan"))
                gross = sum(x["gross_pct"] for x in xs) / len(xs) if xs else None
                cost = sum(x["cost_pct"] for x in xs) / len(xs) if xs else None
                sig = s["n"] >= min_n and lo > 0
                if part == "disc":
                    disc_ok = sig
                    karar = "anlamlı" if sig else ("n yetersiz" if s["n"] < min_n else "—")
                else:
                    if not disc_ok:
                        karar = "keşifte elendi"
                    elif sig:
                        karar = "**GEÇTİ**"
                        decision_cells.append((sc.name, key, s, lo, hi))
                    else:
                        karar = "n yetersiz" if s["n"] < min_n else "doğrulanamadı"
                out.append(f"| {st} | {tag} | {d} | {h} dk | {'keşif' if part == 'disc' else 'doğrulama'} | {s['n']} | {fmt(gross)} | {fmt(cost)} | **{fmt(s['mean'])}** | {fmt(s['median'])} | {fmt(s['win_rate'], 2)} | {fmt(lo)} | {fmt(hi)} | {karar} |")
                jcells.append({"scenario": sc.name, "state": st, "tag": tag, "dir": d, "h": h, "part": part, "n": s["n"], "gross": gross, "cost": cost,
                               "mean": s["mean"], "median": s["median"], "win_rate": s["win_rate"], "lo": None if lo != lo else lo, "hi": None if hi != hi else hi, "karar": karar.strip("*")})

    out += ["", "## Sembol × durum", "", "| sembol | " + " | ".join(STATES) + " |", "|---|" + "---|" * len(STATES)]
    for sym in sorted(sym_state):
        out.append(f"| {sym} | " + " | ".join(str(sym_state[sym][s]) for s in STATES) + " |")
    out += ["", "## Karar (ADR 0008 §8/§10)", ""]
    if decision_cells:
        out.append("Doğrulama bölümünde koşulları sağlayan hücreler:")
        for name, (st, tag, d, h), s, lo, hi in decision_cells:
            out.append(f"- {name}: {st}/{tag}/{d}/{h} dk — n={s['n']}, net ort {s['mean']:.3f}%, CI [{lo:.3f}, {hi:.3f}]")
    else:
        out.append("**Hiçbir hücre doğrulama koşullarını sağlamıyor.** Veri süresi ≥ 3 gün değilse sonuç 'yetersiz veri' olarak okunur; ≥ 3 günde bu DUR kararıdır (proje sahibine sunulur).")
    if hours < 72:
        out.append(f"\n> Veri {hours:.1f} saat (< 72). Bu rapor ÖN rapordur; ADR 0008 §11 nihai karar için ≥ 3 gün ister.")
    body = "\n".join(out)
    print(body)
    rh = hashlib.sha256(body.encode()).hexdigest()[:16]
    print(f"\nRapor hash: `{rh}`")
    if a.json_out:
        Path(a.json_out).write_text(json.dumps({"hours": hours, "symbols": len(by_sym), "bars": sum(len(v) for v in by_sym.values()), "config_hash": cfg_hash,
                                                "state_counts": {s: state_counts[s] for s in STATES}, "transitions": {f"{a_}>{b_}": n for (a_, b_), n in transitions.items()},
                                                "cells": jcells, "passed": len(decision_cells), "hash": rh}, indent=0))


if __name__ == "__main__":
    main(sys.argv[1:])
