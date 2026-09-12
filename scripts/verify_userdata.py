"""Gate 3b offline doğrulama: kayda düşen private çerçeveleri eşleyiciden geçirir ve raporlar.

Shadow modun amacı buydu: çekirdek tüketmeden gerçek veriyi toplamak, sonra kayıt üzerinden
`map_user_event`'in her olay tipini doğru eşlediğini ve hangi alanların **eksik** kaldığını
görmek. Eksik alan uydurulmaz; raporda "yok" olarak görünür.

Ayrıca teslim gecikmesi ölçülür: borsa olay damgası (`T`) → bizim alım damgası (`recv_ns`).

Kullanım: python -m scripts.verify_userdata data/recordings/testnet [--max-files N]
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

from fbot.gateway.userdata_map import map_user_event


def pct(xs: list[float], q: float):
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 1)


def scan(run_dir: Path, max_files: int | None) -> dict:
    files = sorted(run_dir.glob("events-*.jsonl.gz"))
    if max_files:
        files = files[-max_files:]
    types: Counter = Counter()
    kinds: Counter = Counter()
    unmapped: list = []
    missing: Counter = Counter()
    lat_ms: list[float] = []
    samples: dict = {}
    frames = 0
    for path in files:
        with gzip.open(path, "rt") as f:
            while True:
                try:
                    line = f.readline()
                except (EOFError, OSError):
                    break
                if not line:
                    break
                if '"c":"private"' not in line:
                    continue
                try:
                    ev = json.loads(line)
                except ValueError:
                    break
                msg = ev.get("d") or {}
                frames += 1
                etype = msg.get("e", "?")
                types[etype] += 1
                t_ms = msg.get("T") or msg.get("E")
                if t_ms and ev.get("r"):
                    lat_ms.append(ev["r"] / 1e6 - t_ms)
                mapped = map_user_event(msg)
                if mapped is None:
                    kinds["<eşlenmedi>"] += 1
                    if etype not in [u["e"] for u in unmapped]:
                        unmapped.append({"e": etype, "ornek": json.dumps(msg)[:300]})
                    continue
                kinds[mapped["kind"]] += 1
                samples.setdefault(mapped["kind"], mapped)
                for field in ("trade_id", "order_id", "pos_id"):
                    if field not in mapped:
                        missing[f"{mapped['kind']}.{field}"] += 1
    return {"files": len(files), "private_frames": frames, "event_types": dict(types.most_common()),
            "mapped_kinds": dict(kinds.most_common()),
            "unmapped_types": unmapped,
            "missing_fields": dict(missing.most_common()),
            "delivery_lag_ms": {"n": len(lat_ms), "p50": pct(lat_ms, 0.5), "p95": pct(lat_ms, 0.95),
                                "p99": pct(lat_ms, 0.99), "max": round(max(lat_ms), 1) if lat_ms else None},
            "samples": samples}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    out = scan(Path(a.run_dir), a.max_files)
    text = json.dumps(out, ensure_ascii=False, indent=1, default=str)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
