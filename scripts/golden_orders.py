"""Emir düzeyi golden baseline'ı üretir: giriş → koruma → çıkış zincirinin tam komut dizisi.

`tests/golden/replay_baseline.json` yalnız `rec-mini` fixture'ını kapsıyor ve o fixture'da strateji
kapalı olduğu için **yalnız `BarClosed`** üretiliyor. Yani emir alanlarındaki (tetik fiyatı,
`client_id`, `client_algo_id`) bir davranış değişikliği o baseline'ı kırmıyordu.

Bu betik sentetik ama deterministik senaryonun (`tests/scenario.py`) ürettiği komut dizisini
alan alan dosyaya yazar. Planlı re-baseline noktalarında yeniden üretilir ve fark tablosu
`scripts/golden_orders.py --diff <eski.json>` ile çıkarılır.

Kullanım:
    python -m scripts.golden_orders --out tests/golden/orders_baseline.json
    python -m scripts.golden_orders --diff tests/golden/orders_baseline.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from dataclasses import fields
from decimal import Decimal
from pathlib import Path

NOTE = ("Emir düzeyi davranış baseline'ı. Değişirse davranış değişmiştir; planlı re-baseline "
        "dışında değişmesi bugdur. Güncelleme bir ADR ve komut düzeyi diff tablosu gerektirir.")


def _row(c) -> dict:
    out = {"cmd": type(c).__name__}
    for f in fields(c):
        v = getattr(c, f.name)
        out[f.name] = format(v, "f") if isinstance(v, Decimal) else v
    return out


def build() -> dict:
    from fbot.core.commands import canonical
    from tests.scenario import discovered_cells, live_run
    cells = discovered_cells()
    _, trader = live_run(cells)
    cmds = [c for c in trader.commands if type(c).__name__ != "BarClosed"]
    h = hashlib.sha256()
    for c in cmds:
        h.update(canonical(c))
        h.update(b"\n")
    return {"scenario": "tests/scenario.py::live_run(discovered_cells())",
            "hash": h.hexdigest(), "commands": len(cmds),
            "by_kind": dict(sorted(Counter(type(c).__name__ for c in cmds).items())),
            "rows": [_row(c) for c in cmds], "not": NOTE}


def diff(old: dict, new: dict) -> dict:
    """Alan düzeyi fark: hangi komutun hangi alanı değişti. Satır sayısı değişirse ayrıca raporlanır."""
    fields_changed: Counter = Counter()
    examples: dict = {}
    n = min(len(old["rows"]), len(new["rows"]))
    for i in range(n):
        a, b = old["rows"][i], new["rows"][i]
        if a.get("cmd") != b.get("cmd"):
            fields_changed["__cmd_type__"] += 1
            examples.setdefault("__cmd_type__", {"i": i, "eski": a.get("cmd"), "yeni": b.get("cmd")})
            continue
        for k in sorted(set(a) | set(b)):
            if a.get(k) != b.get(k):
                fields_changed[f"{a['cmd']}.{k}"] += 1
                examples.setdefault(f"{a['cmd']}.{k}", {"i": i, "eski": a.get(k), "yeni": b.get(k)})
    return {"hash_changed": old["hash"] != new["hash"],
            "commands": {"eski": old["commands"], "yeni": new["commands"]},
            "by_kind_changed": old["by_kind"] != new["by_kind"],
            "changed_fields": dict(fields_changed.most_common()), "examples": examples}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--diff", help="bu dosyadaki baseline ile bugünkü davranışı karşılaştır")
    a = ap.parse_args(argv)
    new = build()
    if a.diff:
        old = json.loads(Path(a.diff).read_text())
        print(json.dumps(diff(old, new), ensure_ascii=False, indent=1))
        return
    text = json.dumps(new, ensure_ascii=False, indent=1)
    if a.out:
        Path(a.out).write_text(text + "\n")
        print(json.dumps({"yazıldı": a.out, "hash": new["hash"], "commands": new["commands"]}, ensure_ascii=False))
    else:
        print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
