"""Parametre duyarlılık taraması — YALNIZCA keşif bölümü (ADR 0008 §8). Doğrulama verisine dokunmaz.
Kullanım: python -m scripts.research_scan data/research/<run>/bars.jsonl [--config config/research.toml]
Çıktı: W × (p_lo,p_hi) ızgarasında durum dağılımı ve keşif hücrelerinin n / net ort. özeti."""
from __future__ import annotations

import argparse
import json
import sys
import tomllib
from collections import Counter, defaultdict
from pathlib import Path

from fbot.research.features import FeatureConfig, compute_features
from fbot.research.forward import CostScenario, forward_samples
from fbot.research.states import STATES, StateConfig, directions, label_state
from fbot.research.stats import summarize

GRID_W = [120, 240, 480]
GRID_P = [(0.2, 0.8), (0.1, 0.9), (0.3, 0.7)]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("bars")
    ap.add_argument("--config", default="config/research.toml")
    a = ap.parse_args(argv)
    cfg = tomllib.loads(Path(a.config).read_text())
    horizons = cfg["horizons"]["minutes"]
    bar_ms = cfg["bars"]["bar_ms"]
    sc = CostScenario(**cfg["costs"]["scenarios"][0])
    disc = cfg["sampling"]["discovery_frac"]
    by_sym = defaultdict(list)
    for line in Path(a.bars).read_text().splitlines():
        if line.strip():
            b = json.loads(line); by_sym[b["symbol"]].append(b)
    all_t = sorted(b["end_ms"] for bars in by_sym.values() for b in bars)
    split_ms = all_t[int(len(all_t) * disc)]
    # keşif bölümü: yalnızca split_ms öncesi barlar (doğrulama barları belleğe bile alınmaz)
    disc_syms = {s: [b for b in bars if b["end_ms"] < split_ms] for s, bars in by_sym.items()}
    print(f"# Duyarlılık taraması (yalnızca keşif, {sum(len(v) for v in disc_syms.values())} bar, senaryo {sc.name})\n")
    print("| W | p_lo/p_hi | " + " | ".join(STATES[1:]) + " | hücre (n≥30) | en iyi keşif hücresi (net ort %, n) |")
    print("|---|---|" + "---|" * len(STATES[1:]) + "---|---|")
    for W in GRID_W:
        for p_lo, p_hi in GRID_P:
            fcfg = FeatureConfig(W=W, N_short=cfg["features"]["N_short"], N_long=cfg["features"]["N_long"])
            scfg = StateConfig(p_lo=p_lo, p_hi=p_hi)
            counts = Counter(); samples = []
            for sym, bars in disc_syms.items():
                bars = sorted(bars, key=lambda b: b["start_ms"])
                feats = compute_features(bars, fcfg)
                states = [label_state(f, scfg) for f in feats]
                counts.update(states)
                dirs = {i: directions(s, feats[i]) for i, s in enumerate(states) if s != "S0"}
                samples += forward_samples(bars, states, dirs, horizons, sc, bar_ms)
            cells = defaultdict(list)
            for x in samples:
                cells[(x["state"], x["tag"], x["dir"], x["h"])].append(x["net_pct"])
            big = {k: summarize(v) for k, v in cells.items() if len(v) >= 30}
            best = max(big.items(), key=lambda kv: kv[1]["mean"]) if big else None
            best_s = f"{best[0][0]}/{best[0][1]}/{best[0][2]}/{best[0][3]}dk: {best[1]['mean']:.3f} (n={best[1]['n']})" if best else "—"
            print(f"| {W} | {p_lo}/{p_hi} | " + " | ".join(str(counts[s]) for s in STATES[1:]) + f" | {len(big)} | {best_s} |")
    print("\nNot: bu tablo yalnızca keşif bölümüdür; hiçbir hücre burada 'geçmiş' sayılmaz. Nihai karar `research_report` doğrulama bölümündedir.")


if __name__ == "__main__":
    main(sys.argv[1:])
