"""Kayıttan likidasyon akışını çıkarır: `forceOrder` olayları → dakikalık JSONL.

Bu veri Binance arşivinde yok (`liquidationSnapshot` yayınlanmıyor), yalnızca kendi kaydımızda var.
Ham satırlarda bayt düzeyinde ön eleme yapılır; JSON yalnızca aday satırlar için çözülür.

Kayıt sürerken çalıştırılabilir: açık dosyanın gzip bitiş işareti yoktur, bu dosya son tam satıra
kadar okunur ve kesik olarak sayılır. Çökmek yerine eldeki veriyle devam edilir.

Kullanım: python -m scripts.extract_liquidations data/recordings/<run> <out.jsonl>
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path

from fbot.research.liquidation import liq_per_minute, parse_force_order

NEEDLE = b'"forceOrder"'


def extract(run_dir: Path, out: Path, max_files: int | None = None) -> dict:
    files = sorted(Path(run_dir).glob("events-*.jsonl.gz"))
    if max_files:
        files = files[:max_files]
    rows, scanned, bad, truncated = [], 0, 0, 0
    for p in files:
        try:
            with gzip.open(p, "rb") as f:
                for line in f:
                    scanned += 1
                    if NEEDLE not in line:
                        continue
                    try:
                        d = json.loads(line)["d"]["data"]
                    except (ValueError, KeyError, TypeError):
                        bad += 1
                        continue
                    r = parse_force_order(d)
                    if r:
                        rows.append(r)
        except (EOFError, OSError):
            truncated += 1          # hâlâ yazılan dosya: son tam satıra kadar okundu
    per = liq_per_minute(rows)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fo:
        for (sym, minute) in sorted(per):
            fo.write(json.dumps({"symbol": sym, "start_ms": minute, **per[(sym, minute)]},
                                separators=(",", ":")) + "\n")
    return {"files": len(files), "truncated_files": truncated, "lines_scanned": scanned,
            "liquidations": len(rows), "minutes": len(per), "malformed": bad, "out": str(out)}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("out")
    ap.add_argument("--max-files", type=int, default=None)
    a = ap.parse_args(argv)
    print(json.dumps(extract(Path(a.run_dir), Path(a.out), a.max_files)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
