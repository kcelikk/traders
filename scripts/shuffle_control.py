"""Karıştırma (permütasyon) kontrolü: durum etiketleri rastgele karıştırılınca kaç birleşim "geçiyor"?

Etiketler karışınca sinyal yok olur ama fiyat serisi, sürüklenme, giriş sayısı ve kovalanma yapısı
aynı kalır. Gerçek veride geçen birleşim sayısı, karışık veride geçenden anlamlı ölçüde fazla
değilse, "geçti" sonucu çoklu test artefaktıdır.

Kullanım:
    PYTHONPATH=. python -m scripts.shuffle_control <bars.jsonl> <senaryo> <tf_dk> <stride> <tekrar>

p değeri: (gerçeği yakalayan karışık tekrar + 1) / (tekrar + 1). 20 tekrarla ulaşılabilecek en
küçük değer 0,048'dir; daha küçük bir p iddia edilemez.
"""
import json
import random
import sys
import tomllib
from pathlib import Path

from fbot.research.costs import pick, scenarios_from_config
from fbot.research.features import FeatureConfig
from fbot.research.states import StateConfig
from fbot.research.timeframe import aggregate
from scripts.barrier_scan import label_all, load_bars, scan

BARS, SCEN, TF, STRIDE, SEEDS = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
cfg = tomllib.load(open("config/research.toml", "rb"))
f, st, bs, sm = cfg["features"], cfg["states"], cfg["bootstrap"], cfg["sampling"]
cost = pick(scenarios_from_config(cfg), SCEN)
fcfg, scfg = FeatureConfig(W=f["W"], N_short=f["N_short"], N_long=f["N_long"]), StateConfig(st["p_lo"], st["p_hi"])

base = load_bars(Path(BARS))
by = {s: aggregate(r, TF) for s, r in base.items()}
by = {s: r for s, r in by.items() if len(r) > 2 * fcfg.W + fcfg.N_long}
real_labels = label_all(by, fcfg, scfg)

def run(labels, tag):
    rows = scan(by, labels, cost, sm["discovery_frac"], bs["n_boot"], bs["seed"], bs["alpha"],
                sm["min_n"], stride=STRIDE, screen_boot=300)
    n = sum(1 for r in rows if r["gecti"])
    best = max((r["val_mean"] for r in rows), default=float("nan"))
    print(json.dumps({"tag": tag, "birleşim": len(rows), "geçen": n, "en_iyi_doğrulama": round(best, 4)}), flush=True)
    return n

real = run(real_labels, "gerçek")
shuffled = []
for seed in range(SEEDS):
    rng = random.Random(1000 + seed)
    lab = {}
    for s, seq in real_labels.items():
        idx = [i for i, x in enumerate(seq) if x]          # yalnızca etiketli barları karıştır
        vals = [seq[i] for i in idx]
        rng.shuffle(vals)
        out = list(seq)
        for i, v in zip(idx, vals):
            out[i] = v
        lab[s] = out
    shuffled.append(run(lab, f"karışık-{seed}"))
print(json.dumps({"özet": {"gerçek_geçen": real, "karışık_geçen": shuffled,
                           "karışık_ortalama": round(sum(shuffled) / len(shuffled), 2) if shuffled else None}}))
