"""Re-baseline raporu: iki kod sürümünün **komut düzeyinde** farkı (Gate 4e).

`scripts/golden_orders.py --diff` tek senaryoyu karşılaştırır. Bu betik gerçek bir kayıt üzerinde
çalışır ve farkı **karar tipine göre** ayırır:

  · **Giriş kararı farkı sıfır olmalıdır.** Sıfır değilse bu bir bug'dır, re-baseline değil.
  · Çıkış farkları beklenir ve tek tek raporlanır: hangi komut, hangi alan, hangi sequence.

Kullanım:
    python -m scripts.rebaseline_report data/recordings/testnet --out eski.json      # önce (eski kodda)
    python -m scripts.rebaseline_report data/recordings/testnet --diff eski.json     # sonra (yeni kodda)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import fields
from decimal import Decimal
from pathlib import Path

from fbot.core.commands import is_shadow
from fbot.replay.harness import DEFAULT_CFG, iter_lines
from fbot.core.engine import CoreState, Engine
from fbot.clock import ReplayClock
from fbot.events import decode

ENTRY_KINDS = ("PlaceOrder",)          # giriş: reduce_only=False olanlar
EXIT_KINDS = ("PlaceOrder", "PlaceAlgo", "CancelAlgo", "CancelOrder")


def _row(seq: int, c) -> dict:
    out = {"seq": seq, "cmd": type(c).__name__}
    for f in fields(c):
        v = getattr(c, f.name)
        out[f.name] = format(v, "f") if isinstance(v, Decimal) else v
    return out


def collect(run_dir: Path, max_files: int | None, cfg=DEFAULT_CFG) -> dict:
    engine, state, clock = Engine(cfg), CoreState(), ReplayClock()
    rows, shadow = [], []
    n = 0
    for line in iter_lines(run_dir, max_files):
        ev = decode(line)
        clock.set(ev.recv_ns)
        state, cmds = engine.step(state, ev, clock.now_ns())
        n += 1
        for c in cmds:
            (shadow if is_shadow(c) else rows).append(_row(ev.seq, c))
    return {"run_dir": str(run_dir), "max_files": max_files, "events": n,
            "commands": len(rows), "shadow_commands": len(shadow),
            "by_kind": dict(sorted(Counter(r["cmd"] for r in rows).items())), "rows": rows}


def _key(r: dict) -> tuple:
    return (r["seq"], r["cmd"], r.get("client_id") or r.get("client_algo_id") or r.get("symbol", ""))


def diff(old: dict, new: dict, limit: int = 20) -> dict:
    a = {_key(r): r for r in old["rows"]}
    b = {_key(r): r for r in new["rows"]}
    added = [b[k] for k in b.keys() - a.keys()]
    removed = [a[k] for k in a.keys() - b.keys()]
    changed, fields_changed = [], Counter()
    for k in a.keys() & b.keys():
        d = {f: (a[k][f], b[k][f]) for f in set(a[k]) | set(b[k]) if a[k].get(f) != b[k].get(f)}
        if d:
            changed.append({"key": list(k), "alanlar": d})
            for f in d:
                fields_changed[f"{a[k]['cmd']}.{f}"] += 1

    def is_entry(r):
        return r["cmd"] == "PlaceOrder" and r.get("reduce_only") is False

    entry_delta = {"eklenen": sum(1 for r in added if is_entry(r)),
                   "silinen": sum(1 for r in removed if is_entry(r)),
                   "degisen": sum(1 for c in changed if c["key"][1] == "PlaceOrder")}
    return {"baseline_hash_rows": len(old["rows"]), "new_hash_rows": len(new["rows"]),
            "events": {"eski": old["events"], "yeni": new["events"]},
            "by_kind": {"eski": old["by_kind"], "yeni": new["by_kind"]},
            "commands_added": len(added), "commands_removed": len(removed), "commands_changed": len(changed),
            "changed_fields": dict(fields_changed.most_common()),
            "entry_delta": entry_delta,
            "entry_delta_sifir_mi": entry_delta == {"eklenen": 0, "silinen": 0, "degisen": 0},
            "ilk_farklar": (added[:limit], removed[:limit], changed[:limit]),
            "etkilenen_sembol": sorted({r.get("symbol") for r in added + removed if r.get("symbol")}),
            "shadow": {"eski": old["shadow_commands"], "yeni": new["shadow_commands"]}}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--max-files", type=int, default=1)
    ap.add_argument("--out", help="bugünkü davranışı bu dosyaya yaz (baseline)")
    ap.add_argument("--diff", help="bu baseline ile bugünkü davranışı karşılaştır")
    a = ap.parse_args(argv)
    cur = collect(Path(a.run_dir), a.max_files)
    if a.diff:
        old = json.loads(Path(a.diff).read_text())
        r = diff(old, cur)
        print(json.dumps(r, ensure_ascii=False, indent=1, default=str))
        return 0 if r["entry_delta_sifir_mi"] else 1      # giriş farkı = bug
    text = json.dumps(cur, ensure_ascii=False, indent=1, default=str)
    if a.out:
        Path(a.out).write_text(text + "\n")
        print(json.dumps({"yazıldı": a.out, "events": cur["events"], "commands": cur["commands"]}, ensure_ascii=False))
    else:
        print(json.dumps({k: v for k, v in cur.items() if k != "rows"}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
