"""Kayıt akışından canlı görünüm: çekirdek (Faz 2) + durum etiketleme (Faz 3) + recorder istatistikleri. I/O yok; olaylar dışarıdan beslenir."""
from __future__ import annotations

import json
import re
from collections import Counter, deque
from decimal import Decimal

from fbot.core.commands import BarClosed, StalenessChanged
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.events import RawEvent
from fbot.research.features import FeatureConfig, compute_features
from fbot.research.states import STATES, StateConfig, label_state

_ROW = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|")


def parse_phase_table(md: str) -> list[dict]:
    out = []
    for line in md.splitlines():
        m = _ROW.match(line)
        if not m:
            continue
        n, title, status = int(m.group(1)), m.group(2), m.group(3)
        st = "done" if "KAPANDI" in status else ("active" if ("AKTİF" in status or "teslim" in status) else "pending")
        out.append({"n": n, "title": title.strip("* "), "status": st, "note": status.replace("*", "")[:80]})
    return out


class LiveView:
    def __init__(self, symbols: list[str], W: int = 240, N_short: int = 5, N_long: int = 15, p_lo: float = 0.2, p_hi: float = 0.8, bar_ms: int = 60_000):
        self.symbols = symbols
        self.engine = Engine(CoreConfig(bar_ms=bar_ms, staleness_ms={"public": 30_000, "market": 30_000}))
        self.state = CoreState()
        self.fcfg, self.scfg = FeatureConfig(W=W, N_short=N_short, N_long=N_long), StateConfig(p_lo, p_hi)
        self.bars: dict[str, list] = {s: [] for s in symbols}
        self.labels: dict[str, str] = {s: "S0" for s in symbols}
        self.label_since: dict[str, int] = {}
        self.features: dict[str, dict] = {}
        self.transitions: Counter = Counter()
        self.state_counts: Counter = Counter()
        self.log: deque = deque(maxlen=60)
        self.run: dict = {}
        self.stats: dict = {}
        self.connects: Counter = Counter()
        self.stale_events = 0
        self.snapshots = 0
        self.stale_flags: dict[str, bool] = {}
        self.alarms: list = []

    def _push(self, t_ns: int, kind: str, msg: str):
        self.log.appendleft({"t_ns": t_ns, "kind": kind, "msg": msg})

    def feed(self, ev: RawEvent):
        if ev.cat == "ctrl":
            try:
                info = json.loads(ev.raw.decode())
            except ValueError:
                info = {}
            if ev.stream == "run_start":
                self.run = {k: info.get(k) for k in ("run_id", "restart_no", "git_sha", "config_hash", "start_ns", "symbols")}
                self._push(ev.recv_ns, "RUN", f"run_start {info.get('run_id')} restart={info.get('restart_no')} git={info.get('git_sha')}")
            elif ev.stream == "connect":
                self.connects[info.get("cat")] += 1
                self._push(ev.recv_ns, "CONNECT", f"{info.get('cat')} bağlandı #{info.get('n')} · {info.get('connect_ms')} ms")
            elif ev.stream in ("disconnect", "reconnect_wait", "force_reconnect"):
                self._push(ev.recv_ns, "DISCONNECT", f"{info.get('cat')} {ev.stream} {info.get('reason', '')}")
            elif ev.stream == "stale":
                self.stale_events += 1
                self._push(ev.recv_ns, "STALE", f"{info.get('cat')} {info.get('age_s')} s (eşik {info.get('threshold_s')} s)")
            elif ev.stream == "snapshot":
                self.snapshots += 1
            elif ev.stream == "stats":
                self.stats = info
            elif ev.stream == "alarm":
                self.alarms.insert(0, {"t_ns": ev.recv_ns, **info})
                del self.alarms[20:]
                self._push(ev.recv_ns, "ALARM", f"{info.get('kind')} · {info.get('detail', '')[:90]}")
        state, cmds = self.engine.step(self.state, ev, ev.recv_ns)
        for c in cmds:
            if isinstance(c, BarClosed):
                self._on_bar(c, ev.recv_ns)
            elif isinstance(c, StalenessChanged):
                self.stale_flags[c.category] = c.stale
                self._push(ev.recv_ns, "STALE" if c.stale else "INFO", f"{c.category} {'bayat' if c.stale else 'taze'} · {c.age_ms} ms")

    def _on_bar(self, b: BarClosed, t_ns: int):
        lst = self.bars.setdefault(b.symbol, [])
        m = self.state.markets.get(b.symbol)
        spread = None
        if m is not None and m.best_bid is not None and m.best_ask:
            spread = float((m.best_ask - m.best_bid) / m.best_ask * 10000)
        lst.append({"start_ms": b.start_ms, "end_ms": b.end_ms, "symbol": b.symbol, "o": float(b.open), "h": float(b.high), "l": float(b.low), "c": float(b.close),
                    "open": float(b.open), "high": float(b.high), "low": float(b.low), "close": float(b.close),
                    "volume": float(b.volume), "buy_volume": float(b.buy_volume), "trades": b.trades, "spread_bps": spread})
        keep = 2 * self.fcfg.W + self.fcfg.N_long + 80   # 2W: persentilin persentili (bkz. core/state_engine._keep)
        if len(lst) > keep:
            del lst[:-keep]
        f = compute_features(lst, self.fcfg)[-1]
        self.features[b.symbol] = f
        new = label_state(f, self.scfg)
        old = self.labels.get(b.symbol, "S0")
        self.state_counts[new] += 1
        self.transitions[(old, new)] += 1
        if new != old:
            self.label_since[b.symbol] = len(lst)
            self._push(t_ns, "SİNYAL", f"{b.symbol} {old}→{new} · ret_long p{self._p(f.get('pct_ret_long'))} · rv_long p{self._p(f.get('pct_rv_long'))}")
        self.labels[b.symbol] = new

    @staticmethod
    def _p(x):
        return "—" if x is None else f"{x * 100:.0f}"

    def confidence(self, f: dict, st: str) -> float | None:
        lo, hi = self.scfg.p_lo, self.scfg.p_hi
        pr, prv = f.get("pct_ret_long"), f.get("pct_rv_long")
        if st == "S1" and pr is not None and prv is not None:
            return round(min(pr - hi, prv - lo, hi - prv), 2)
        if st == "S2" and pr is not None and prv is not None:
            return round(min(lo - pr, prv - lo, hi - prv), 2)
        if st == "S3" and prv is not None:
            return round(lo - prv, 2)
        if st == "S4" and f.get("pct_rv_short") is not None and f.get("pct_vol_ratio") is not None:
            return round(min(f["pct_rv_short"] - hi, f["pct_vol_ratio"] - hi), 2)
        return None

    def snapshot(self, now_ns: int) -> dict:
        uni = []
        for s in self.symbols:
            m = self.state.markets.get(s)
            f = self.features.get(s, {})
            bars = self.bars.get(s, [])
            st = self.labels.get(s, "S0")
            spread = None
            if m is not None and m.best_bid is not None and m.best_ask:
                spread = float((m.best_ask - m.best_bid) / m.best_ask * 10000)
            uni.append({"sym": s, "price": str(m.best_ask) if m and m.best_ask is not None else None, "bid": str(m.best_bid) if m and m.best_bid is not None else None,
                        "mark": str(m.mark_price) if m and m.mark_price is not None else None, "funding_rate": str(m.funding_rate) if m and m.funding_rate is not None else None,
                        "spread_bps": spread, "state": st, "conf": self.confidence(f, st), "bars": len(bars),
                        "age_bars": (len(bars) - self.label_since[s]) if s in self.label_since else len(bars),
                        "warm_pct": min(100, int(len(bars) / (2 * self.fcfg.W) * 100)) if self.fcfg.W else 100,
                        "features": {k: (None if v is None else round(v, 6)) for k, v in f.items()}})
        stale_age = {cat: (now_ns - t) / 1e9 for cat, t in self.state.last_recv_ns.items()}
        return {
            "universe": uni,
            "bars": {s: [{"t": b["start_ms"], "o": b["o"], "h": b["h"], "l": b["l"], "c": b["c"], "v": b["volume"]} for b in self.bars.get(s, [])[-72:]] for s in self.symbols},
            "recorder": {**self.run, "events": self.state.events, "seq": self.state.last_seq, "loop_lag_p50": self.stats.get("loop_lag_ms", {}).get("p50"),
                         "loop_lag_p99": self.stats.get("loop_lag_ms", {}).get("p99"), "loop_lag_max": self.stats.get("loop_lag_ms", {}).get("max"),
                         "queue": self.stats.get("queue"), "dropped": self.stats.get("dropped"), "connects": dict(self.connects), "stale_events": self.stale_events,
                         "snapshots": self.snapshots, "parse_errors": self.state.parse_errors},
            "stale": stale_age, "stale_flags": dict(self.stale_flags),
            "feed": list(self.log), "alarms": list(self.alarms),
            "state_counts": {s: self.state_counts.get(s, 0) for s in STATES},
            "transitions": {f"{a}>{b}": n for (a, b), n in self.transitions.items()},
        }
