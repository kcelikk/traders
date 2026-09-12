"""Replay harness: kayıt → ReplayClock → Engine.step → komut hash zinciri. I/O kenarı."""
from __future__ import annotations

import gzip
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from fbot.clock import ReplayClock
from fbot.core.commands import canonical, is_shadow
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.events import decode

DEFAULT_CFG = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000})


@dataclass
class ReplayResult:
    hash: str
    events: int
    commands: int
    shadow_hash: str = ""
    shadow_commands: int = 0
    by_kind: dict[str, int] = field(default_factory=dict)
    first_seq: int | None = None
    last_seq: int | None = None
    elapsed_s: float = 0.0
    events_per_s: float = 0.0
    parse_errors: int = 0


def iter_lines(run_dir: Path, max_files: int | None = None):
    files = sorted(Path(run_dir).glob("events-*.jsonl.gz"))
    if max_files:
        files = files[:max_files]
    for path in files:
        try:
            with gzip.open(path, "rb") as f:
                for line in f:
                    if line.endswith(b"\n"):
                        yield line
        except (EOFError, OSError):
            return


def replay(run_dir: Path, cfg: CoreConfig = DEFAULT_CFG, max_files: int | None = None, max_events: int | None = None,
           adapter=None) -> ReplayResult:
    engine, state, clock = Engine(cfg), CoreState(), ReplayClock()
    h = hashlib.sha256()
    hs = hashlib.sha256()      # shadow zinciri ayrı: gözlem çıktısı ana hash'i kirletmez
    nshadow = 0
    n = ncmd = 0
    by_kind: dict[str, int] = {}
    first = last = None
    t0 = time.perf_counter()
    for line in iter_lines(run_dir, max_files):
        ev = decode(line)
        clock.set(ev.recv_ns)
        state, cmds = engine.step(state, ev, clock.now_ns())
        n += 1
        first = first if first is not None else ev.seq
        last = ev.seq
        for c in cmds:
            k = type(c).__name__
            by_kind[k] = by_kind.get(k, 0) + 1
            if is_shadow(c):
                hs.update(b"%d|" % ev.seq)
                hs.update(canonical(c))
                hs.update(b"\n")
                nshadow += 1
                continue        # shadow emir üretmez: adapter'a da gitmez
            h.update(b"%d|" % ev.seq)
            h.update(canonical(c))
            h.update(b"\n")
            ncmd += 1
            if adapter is not None:
                adapter.submit(c)
        if max_events and n >= max_events:
            break
    el = time.perf_counter() - t0
    return ReplayResult(h.hexdigest(), n, ncmd, hs.hexdigest() if nshadow else "", nshadow,
                        by_kind, first, last, el, n / el if el else 0.0, state.parse_errors)
