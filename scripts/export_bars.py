"""Artımlı replay → bar serisi (JSONL). Kullanım: python -m scripts.export_bars data/recordings/<run> data/research/<run>/bars.jsonl [--max-files N]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fbot.replay.export import export_bars


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("out")
    ap.add_argument("--max-files", type=int, default=None)
    a = ap.parse_args(argv)
    print(json.dumps(export_bars(Path(a.run_dir), Path(a.out), max_files=a.max_files)))


if __name__ == "__main__":
    main(sys.argv[1:])
