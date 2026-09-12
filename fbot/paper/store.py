"""Paper kalıcılık: SQLite (stdlib), write-behind tampon, tek yazar. I/O kenarı.

Hot path'te değildir: çekirdek komut üretir, buradaki kayıt görünüm ve rapor içindir (docs/design/faz7-paper-trading.md §2).
"""
from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from fbot.identity import ROW_COLS, RunIdentity

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY, run_id TEXT, t_ms INTEGER, symbol TEXT, kind TEXT, reasons TEXT, cell TEXT, explain TEXT);
CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY, run_id TEXT, seq INTEGER, t_ns INTEGER, cmd TEXT, symbol TEXT, side TEXT, type TEXT, qty TEXT, client_id TEXT, payload TEXT);
CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY, run_id TEXT, seq INTEGER, t_ns INTEGER, kind TEXT, symbol TEXT, price TEXT, qty TEXT, client_id TEXT, reason TEXT);
CREATE TABLE IF NOT EXISTS positions (pos_id TEXT PRIMARY KEY, run_id TEXT, symbol TEXT, side TEXT, state TEXT, qty TEXT, entry_price TEXT,
                                      sl TEXT, tp TEXT, net_pct TEXT, exit_reason TEXT, opened_ns INTEGER, closed_ns INTEGER, entry_state TEXT);
CREATE INDEX IF NOT EXISTS ix_dec_t ON decisions(t_ms);
CREATE INDEX IF NOT EXISTS ix_pos_state ON positions(state);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS heartbeat (id INTEGER PRIMARY KEY CHECK (id=1), ts_ns INTEGER, detail TEXT);
CREATE TABLE IF NOT EXISTS runs (run_id TEXT, restart_no INTEGER, started_ns INTEGER, mode TEXT, strategy_id TEXT,
                                 strategy_version TEXT, config_hash TEXT, config_semantic_hash TEXT, code_hash TEXT,
                                 reactor_id TEXT, git_sha TEXT, PRIMARY KEY (run_id, restart_no));
"""

ROW_TABLES = ("decisions", "orders", "fills", "positions")

# Sonradan eklenen sütunlar (eski veritabanları için göç). Yalnız ADD COLUMN; DROP yok.
MIGRATIONS = [("positions", "exit_price", "TEXT"), ("positions", "filled_qty", "TEXT")]
MIGRATIONS += [(t, c, "TEXT") for t in ROW_TABLES for c in ROW_COLS]

_ROW_SQL = ",".join(ROW_COLS)                 # "mode,strategy_id,..."
_ROW_Q = ",".join("?" * len(ROW_COLS))


class PaperStore:
    """Tek yazar. Bağlantı `check_same_thread=False` ile açılır ve **kilitle** korunur:
    `AsyncStore` yazımları ayrı thread'e taşır, okuma/heartbeat ise döngü thread'inden gelir.
    """

    def __init__(self, path: Path, run_id: str | None = None, flush_every: int = 200, env: str | None = None,
                 identity: RunIdentity | None = None, started_ns: int | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.identity = identity
        self.run_id = identity.run_id if identity is not None else run_id
        if not self.run_id:
            raise ValueError("run_id veya identity gerekli")
        self.flush_every = flush_every
        self._lock = threading.RLock()
        self.con = sqlite3.connect(str(self.path), check_same_thread=False)
        self.con.executescript(SCHEMA)
        for table, col, typ in MIGRATIONS:
            cols = {r[1] for r in self.con.execute(f"PRAGMA table_info({table})")}
            if col not in cols:
                self.con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
        self.env = self._resolve_env(identity, env)
        self._row = identity.row() if identity is not None else (self.env, None, None, None, None)
        self.con.executemany("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                             [("env", self.env), ("run_id", self.run_id)])
        if identity is not None:
            self._record_run(identity, started_ns)
        self.con.commit()
        self.pending = 0

    def _resolve_env(self, identity: RunIdentity | None, env: str | None) -> str:
        """Doğruluk sırası: kimlik → çağıranın verdiği değer → `runs` tablosunun son satırı → eski `meta.env`.

        Eski davranışta veritabanındaki değer her şeyi eziyordu (kilit); kimliği veren çağıran artık kazanır.
        """
        if identity is not None:
            return identity.mode
        if env is not None:
            return env
        r = self.con.execute("SELECT mode FROM runs ORDER BY started_ns DESC, restart_no DESC LIMIT 1").fetchone()
        if r and r[0]:
            return r[0]
        m = self.con.execute("SELECT value FROM meta WHERE key='env'").fetchone()
        return m[0] if m else "paper"

    def _record_run(self, i: RunIdentity, started_ns: int | None) -> None:
        """`runs` koşu kimliğinin doğruluk kaynağıdır: her yeniden başlatma ayrı satır."""
        self.con.execute("""INSERT INTO runs(run_id,restart_no,started_ns,mode,strategy_id,strategy_version,config_hash,
                                             config_semantic_hash,code_hash,reactor_id,git_sha)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?)
                            ON CONFLICT(run_id,restart_no) DO UPDATE SET started_ns=excluded.started_ns, mode=excluded.mode,
                            strategy_id=excluded.strategy_id, strategy_version=excluded.strategy_version,
                            config_hash=excluded.config_hash, config_semantic_hash=excluded.config_semantic_hash,
                            code_hash=excluded.code_hash, reactor_id=excluded.reactor_id, git_sha=excluded.git_sha""",
                         (i.run_id, i.restart_no, started_ns, i.mode, i.strategy_id, i.strategy_version, i.config_hash,
                          i.config_semantic_hash, i.code_hash, i.reactor_id, i.git_sha))

    def runs(self) -> list[dict]:
        with self._lock:
            cur = self.con.execute("SELECT run_id,restart_no,started_ns,mode,strategy_id,strategy_version,config_hash,"
                                   "config_semantic_hash,code_hash,reactor_id,git_sha FROM runs ORDER BY started_ns, restart_no")
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    # ---- yazımlar (tamponlu)
    def record_decision(self, d: dict) -> None:
        with self._lock:
            self.con.execute(f"INSERT INTO decisions(run_id,t_ms,symbol,kind,reasons,cell,explain,{_ROW_SQL}) VALUES(?,?,?,?,?,?,?,{_ROW_Q})",
                             (self.run_id, d.get("t_ms"), d.get("symbol"), d.get("kind"), json.dumps(d.get("reasons") or []),
                              d.get("cell"), d.get("explain"), *self._row))
            self._maybe_flush()

    def record_order(self, o: dict) -> None:
        with self._lock:
            self.con.execute(f"INSERT INTO orders(run_id,seq,t_ns,cmd,symbol,side,type,qty,client_id,payload,{_ROW_SQL}) VALUES(?,?,?,?,?,?,?,?,?,?,{_ROW_Q})",
                             (self.run_id, o.get("seq"), o.get("t_ns"), o.get("cmd"), o.get("symbol"), o.get("side"), o.get("type"),
                              o.get("qty"), o.get("client_id") or o.get("client_algo_id"), json.dumps(o, default=str), *self._row))
            self._maybe_flush()

    def record_fill(self, f: dict) -> None:
        with self._lock:
            self.con.execute(f"INSERT INTO fills(run_id,seq,t_ns,kind,symbol,price,qty,client_id,reason,{_ROW_SQL}) VALUES(?,?,?,?,?,?,?,?,?,{_ROW_Q})",
                             (self.run_id, f.get("seq"), f.get("t_ns"), f.get("kind"), f.get("symbol"), f.get("price"), f.get("qty"),
                              f.get("client_id"), f.get("reason"), *self._row))
            self._maybe_flush()

    def record_position(self, p: dict) -> None:
        with self._lock:
            self.con.execute(f"""INSERT INTO positions(pos_id,run_id,symbol,side,state,qty,entry_price,sl,tp,net_pct,exit_reason,opened_ns,closed_ns,entry_state,exit_price,filled_qty,{_ROW_SQL})
                                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,{_ROW_Q})
                                ON CONFLICT(pos_id) DO UPDATE SET state=excluded.state, qty=excluded.qty, sl=excluded.sl, tp=excluded.tp,
                                net_pct=excluded.net_pct, exit_reason=excluded.exit_reason, closed_ns=excluded.closed_ns,
                                exit_price=COALESCE(excluded.exit_price, positions.exit_price),
                                filled_qty=COALESCE(excluded.filled_qty, positions.filled_qty)""",
                             (p["pos_id"], self.run_id, p.get("symbol"), p.get("side"), p.get("state"), p.get("qty"), p.get("entry_price"),
                              p.get("sl"), p.get("tp"), p.get("net_pct"), p.get("exit_reason"), p.get("opened_ns"), p.get("closed_ns"),
                              p.get("entry_state"), p.get("exit_price"), p.get("filled_qty"), *self._row))
            self._maybe_flush()

    # ---- etkin yapılandırma ve canlılık (konsol bunları okur)
    def set_config(self, cfg: dict, config_hash: str, config_semantic_hash: str | None = None) -> None:
        rows = [("config", json.dumps(cfg, default=str)), ("config_hash", config_hash)]
        if config_semantic_hash is not None:
            rows.append(("config_semantic_hash", config_semantic_hash))
        with self._lock:
            self.con.executemany("INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", rows)
            self.flush()

    def get_config(self) -> tuple[dict, str | None]:
        with self._lock:
            rows = dict(self.con.execute("SELECT key, value FROM meta WHERE key IN ('config','config_hash')").fetchall())
        try:
            return json.loads(rows.get("config") or "{}"), rows.get("config_hash")
        except ValueError:
            return {}, rows.get("config_hash")

    def heartbeat(self, now_ns: int, detail: dict) -> None:
        with self._lock:
            self.con.execute("INSERT INTO heartbeat(id,ts_ns,detail) VALUES(1,?,?) ON CONFLICT(id) DO UPDATE SET ts_ns=excluded.ts_ns, detail=excluded.detail",
                             (now_ns, json.dumps(detail, default=str)))
            self.flush()

    def get_heartbeat(self) -> dict | None:
        with self._lock:
            r = self.con.execute("SELECT ts_ns, detail FROM heartbeat WHERE id=1").fetchone()
        if not r:
            return None
        try:
            return {"ts_ns": r[0], "detail": json.loads(r[1] or "{}")}
        except ValueError:
            return {"ts_ns": r[0], "detail": {}}

    def _maybe_flush(self) -> None:
        self.pending += 1
        if self.pending >= self.flush_every:
            self.flush()

    def flush(self) -> None:
        with self._lock:
            self.con.commit()
            self.pending = 0

    def close(self) -> None:
        with self._lock:
            self.flush()
            self.con.close()

    # ---- okuma (hepsi bu koşuya kısıtlı: aynı dosyada birden çok koşu olabilir)
    def summary(self) -> dict:
        r = (self.run_id,)
        with self._lock:
            c = self.con
            by_kind = {k: n for k, n in c.execute("SELECT kind, COUNT(*) FROM decisions WHERE run_id=? GROUP BY kind", r).fetchall()}
            closed = c.execute("SELECT COUNT(*), COALESCE(SUM(CAST(net_pct AS REAL)),0) FROM positions WHERE run_id=? AND state='CLOSED'", r).fetchone()
            reasons = dict(c.execute("SELECT exit_reason, COUNT(*) FROM positions WHERE run_id=? AND exit_reason IS NOT NULL GROUP BY exit_reason", r).fetchall())
            wins = c.execute("SELECT COUNT(*) FROM positions WHERE run_id=? AND state='CLOSED' AND CAST(net_pct AS REAL) > 0", r).fetchone()[0]
            open_n = c.execute("SELECT COUNT(*) FROM positions WHERE run_id=? AND state NOT IN ('CLOSED')", r).fetchone()[0]
            orders = c.execute("SELECT COUNT(*) FROM orders WHERE run_id=?", r).fetchone()[0]
            fills = c.execute("SELECT COUNT(*) FROM fills WHERE run_id=?", r).fetchone()[0]
        return {"decisions": sum(by_kind.values()), "approve": by_kind.get("APPROVE", 0), "reject": by_kind.get("REJECT", 0),
                "resize": by_kind.get("RESIZE", 0), "positions_open": open_n,
                "positions_closed": closed[0], "net_sum_pct": round(closed[1], 6), "win_rate": (wins / closed[0]) if closed[0] else None,
                "exit_reasons": reasons, "orders": orders, "fills": fills}

    def recent_positions(self, n: int = 20) -> list[dict]:
        with self._lock:
            cur = self.con.execute("SELECT pos_id,symbol,side,state,qty,entry_price,sl,tp,net_pct,exit_reason,opened_ns,closed_ns,entry_state "
                                   "FROM positions WHERE run_id=? ORDER BY opened_ns DESC LIMIT ?", (self.run_id, n))
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def recent_decisions(self, n: int = 20) -> list[dict]:
        with self._lock:
            cur = self.con.execute("SELECT t_ms,symbol,kind,reasons,cell,explain FROM decisions WHERE run_id=? ORDER BY id DESC LIMIT ?", (self.run_id, n))
            cols = [d[0] for d in cur.description]
            return [{**dict(zip(cols, r)), "reasons": json.loads(r[3] or "[]")} for r in cur.fetchall()]
