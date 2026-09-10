"""Replay CLI. Kullanım: python -m scripts.replay <run_dir> [--max-files N] [--json]"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict
from pathlib import Path

from fbot.replay.harness import replay


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--max-files", type=int, default=None)
    ap.add_argument("--max-events", type=int, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    r = replay(Path(a.run_dir), max_files=a.max_files, max_events=a.max_events)
    try:
        sha = subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        sha = "unknown"
    d = {**asdict(r), "git_sha": sha, "run_dir": str(a.run_dir)}
    if a.json:
        print(json.dumps(d))
    else:
        for k, v in d.items():
            print(f"{k}: {v}")


if __name__ == "__main__":
    main(sys.argv[1:])
