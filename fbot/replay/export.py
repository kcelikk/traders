"""Artımlı bar export'u. Dosya başına cache: bars parçası + dosya sonu engine state'i (pickle).
Yeni dosya geldiğinde son cache'lenmiş state'ten devam edilir; açık (manifestte olmayan) son dosya cache'lenmez, her seferinde yeniden oynatılır."""
from __future__ import annotations

import gzip
import json
import pickle
from pathlib import Path

from fbot.clock import ReplayClock
from fbot.core.commands import BarClosed
from fbot.core.engine import CoreState, Engine
from fbot.events import decode
from fbot.replay.harness import DEFAULT_CFG


def _bar_row(c: BarClosed, m) -> dict:
    spread = None
    if m.best_bid is not None and m.best_ask is not None and m.best_ask > 0:
        spread = float((m.best_ask - m.best_bid) / m.best_ask * 10000)
    return {
        "symbol": c.symbol, "start_ms": c.start_ms, "end_ms": c.end_ms,
        "open": float(c.open), "high": float(c.high), "low": float(c.low), "close": float(c.close),
        "volume": float(c.volume), "buy_volume": float(c.buy_volume), "trades": c.trades,
        "spread_bps": spread,
        "mark": float(m.mark_price) if m.mark_price is not None else None,
        "index": float(m.index_price) if m.index_price is not None else None,
        "funding_rate": float(m.funding_rate) if m.funding_rate is not None else None,
        "next_funding_ms": m.next_funding_ms,
    }


def _closed_files(run_dir: Path) -> set[str]:
    m = run_dir / "manifest.jsonl"
    if not m.exists():
        return set()
    return {json.loads(l)["file"] for l in m.read_text().splitlines() if l.strip()}


def _load_cache(path: Path):
    """Cache, çekirdek state'inin pickle'ıdır: state şekli değişince eski cache kullanılamaz.
    Uyumsuz veya bozuk cache sessizce atlanır, dosya yeniden oynatılır (çökmek yerine)."""
    try:
        with path.open("rb") as f:
            obj = pickle.load(f)
    except Exception:  # noqa: BLE001 — pickle her sınıf hatasını fırlatabilir
        return None
    if not (isinstance(obj, tuple) and len(obj) == 2 and isinstance(obj[0], CoreState) and isinstance(obj[1], int)):
        return None
    fresh = CoreState()
    if any(not hasattr(obj[0], f) for f in vars(fresh)):
        return None
    return obj


def export_bars(run_dir: Path, out: Path, cfg=DEFAULT_CFG, max_files: int | None = None) -> dict:
    run_dir, out = Path(run_dir), Path(out)
    cache = out.parent / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    files = sorted(run_dir.glob("events-*.jsonl.gz"))
    if max_files:
        files = files[:max_files]
    closed = _closed_files(run_dir)
    engine, clock = Engine(cfg), ReplayClock()
    state = CoreState()
    replayed = cached = 0
    n_events = n_bars = 0
    with out.open("w") as fo:
        for path in files:
            cpart, cstate = cache / (path.name + ".bars.jsonl"), cache / (path.name + ".state.pkl")
            cached_state = _load_cache(cstate) if (cpart.exists() and cstate.exists()) else None
            if cached_state is not None:
                fo.write(cpart.read_text())
                state, clock_ns = cached_state
                clock.set(clock_ns)
                cached += 1
                n_bars += sum(1 for _ in cpart.open())
                continue
            rows = []
            truncated = False
            try:
                with gzip.open(path, "rb") as f:
                    for line in f:
                        if not line.endswith(b"\n"):
                            truncated = True
                            continue
                        ev = decode(line)
                        clock.set(ev.recv_ns)
                        state, cmds = engine.step(state, ev, clock.now_ns())
                        n_events += 1
                        for c in cmds:
                            if isinstance(c, BarClosed):
                                rows.append(json.dumps(_bar_row(c, state.markets[c.symbol]), separators=(",", ":")) + "\n")
            except (EOFError, OSError):
                truncated = True
            text = "".join(rows)
            fo.write(text)
            n_bars += len(rows)
            replayed += 1
            # yalnızca manifestte kapanmış ve kesik olmayan dosyalar cache'lenir
            if path.name in closed and not truncated:
                cpart.write_text(text)
                with cstate.open("wb") as f:
                    pickle.dump((state, clock.now_ns()), f, protocol=pickle.HIGHEST_PROTOCOL)
    return {"files_replayed": replayed, "files_cached": cached, "events_replayed": n_events, "bars": n_bars, "out": str(out)}
