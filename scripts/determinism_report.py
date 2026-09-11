"""Rule Zero raporu: aynı kaydı **iki ayrı process'te** oynatır, hash'leri karşılaştırır, JSON yazar.

Konsol determinizm kutusunda sabit bir hash gösteriyordu (F09). Bu betik gerçek ölçümü üretir;
dosya yoksa konsol "ölçülmedi" yazar. Kullanım:
    python -m scripts.determinism_report <run_dir> [--max-files N] [--out data/research/determinism.json]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


def run_once(run_dir: str, max_files: int | None) -> dict:
    cmd = [sys.executable, "-m", "scripts.replay", run_dir, "--json"]
    if max_files:
        cmd += ["--max-files", str(max_files)]
    return json.loads(subprocess.check_output(cmd).decode())


def report(run_dir: str, max_files: int | None) -> dict:
    a = run_once(run_dir, max_files)
    b = run_once(run_dir, max_files)
    return {"t_ms": int(time.time() * 1000), "run_dir": run_dir, "max_files": max_files,
            "runs": [{"proc": "process 1", "hash": a["hash"], "events": a["events"], "events_per_s": round(a["events_per_s"], 1)},
                     {"proc": "process 2", "hash": b["hash"], "events": b["events"], "events_per_s": round(b["events_per_s"], 1)}],
            "equal": a["hash"] == b["hash"], "events": a["events"], "commands": a["commands"],
            "events_per_s": round(max(a["events_per_s"], b["events_per_s"]), 1), "git_sha": a.get("git_sha")}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--max-files", type=int, default=1)
    ap.add_argument("--out", default="data/research/determinism.json")
    a = ap.parse_args(argv)
    r = report(a.run_dir, a.max_files)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(r, indent=2))
    print(json.dumps(r))
    return 0 if r["equal"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
