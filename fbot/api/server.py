"""Process 4 — api/konsol: kayıt akışını tail eder (bus'sız, ADR 0005/Faz 7 §2), /api/state JSON ve ui/ statik servis.
Yalnızca stdlib. Varsayılan bağlama 127.0.0.1:8787 (SSH tüneli ile erişim). Kârlılık gösterilmedi (ADR 0010)."""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import tomllib
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fbot.api.auth import AuthConfig, check as auth_check
from fbot.api.live_view import LiveView, parse_phase_table
from fbot.api.paper_view import environments, paper_snapshot
from fbot.api.tail import GrowingGzipReader
from fbot.events import decode
from fbot.gateway.killswitch import KillSwitch

ROOT = Path(__file__).resolve().parents[2]

LATENCY_KEYS = {"keep-alive RTT": "rest_rtt", "btcusdt@bookTicker: recv − E": "ws_public_lag", "btcusdt@aggTrade: recv − E": "ws_market_lag",
                "istek → cevap RTT": "wsapi_rtt", "clock skew (server − local orta nokta)": "skew", "yeni bağlantı: TCP+TLS connect": "tcp_connect"}


def parse_latency_md(md: str) -> dict:
    out = {}
    for line in md.splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 8 or cells[0] not in LATENCY_KEYS or cells[0] in ("Seri",):
            continue
        key = LATENCY_KEYS[cells[0]]
        if key in out:
            continue
        try:
            out[key] = {"n": int(cells[1]), "p50": float(cells[2]), "p95": float(cells[3]), "p99": float(cells[4]), "max": float(cells[6])}
        except ValueError:
            pass
    return out


def recorder_files(run_dir: Path) -> list[dict]:
    files = sorted(run_dir.glob("events-*.jsonl.gz"), key=lambda p: p.name, reverse=True)
    return [{"name": p.name, "size": p.stat().st_size} for p in files]


POSITION_DEFAULTS = {"t_protect_ms": 3000, "t_backup_ms": 1500, "working_type": "MARK_PRICE", "price_protect": True, "min_replace_interval_ms": 5000,
                     "taker_fee_pct": "0.05 (VIP0, doğrulanmadı)", "maker_fee_pct": "0.02", "max_hold_ms": None, "lock_trigger_pct": None, "lock_offset_pct": None,
                     "trail_step_pct": None, "trail_gap_pct": None, "tp1_pct": None, "tp1_frac": None, "degrade_map": "{S1:[S2], S2:[S1]}"}
RISK_DEFAULTS = {"max_positions": 5, "gross_cap_usdt": 400, "beta_cap_usdt": None, "daily_loss_limit_pct": None, "cooldown_loss_ms": None, "reserve_orders": 3}
LOCKED = [["Piyasa", "Binance USDⓈ-M Futures · spot yok"], ["Pozisyon modu", "One-way"], ["Sembol evreni", "TOP 10 (maks 20) · 24 s quoteVolume · stablecoin hariç · 00:00 UTC"],
          ["Eşzamanlı pozisyon", "en fazla 5 · Risk Engine sert limit"], ["Kaldıraç", "BTCUSDT/ETHUSDT 10x · diğerleri 5x"], ["İşlem büyüklüğü", "80 USDT notional · step'e aşağı · filtre altı REJECT"],
          ["Emir yolu", "WebSocket API + Ed25519 · REST fallback"], ["Kimlik", "session.logon · userDataStream.start + listenKey (ADR 0003)"],
          ["Açılışta koruma", "SL + TP algo · closePosition=true · deterministik clientAlgoId"], ["Varsayılan mod", "Paper"], ["Hot path", "tek process, tek thread · 1 ms bütçe (ADR 0011)"]]


def assemble_config(cfg_dir: Path) -> dict:
    rec = tomllib.loads((cfg_dir / "recorder.toml").read_text()) if (cfg_dir / "recorder.toml").exists() else {}
    res = tomllib.loads((cfg_dir / "research.toml").read_text()) if (cfg_dir / "research.toml").exists() else {}
    return {"staleness_s": rec.get("staleness_s", {}), "recorder_run": rec.get("run", {}), "universe": rec.get("universe", {}), "streams": rec.get("streams", {}),
            "research": {**res.get("features", {}), **res.get("states", {}), "horizons": res.get("horizons", {}).get("minutes"), "seed": res.get("bootstrap", {}).get("seed")},
            "position": POSITION_DEFAULTS, "risk": RISK_DEFAULTS, "locked": LOCKED}


class Tailer(threading.Thread):
    """Kayıt dizinini izler: geçmiş dosyaları oynatır, sonra açık dosyayı tail eder; dosya döndükçe sıradakine geçer."""

    def __init__(self, run_dir: Path, view: LiveView, lock: threading.Lock, history_files: int):
        super().__init__(daemon=True)
        self.run_dir, self.view, self.lock, self.history_files = run_dir, view, lock, history_files
        self.current: Path | None = None
        self.reader: GrowingGzipReader | None = None
        self.done: set[str] = set()
        self.loading = True
        self.lines = 0

    def _files(self):
        return sorted(self.run_dir.glob("events-*.jsonl.gz"), key=lambda p: p.name)

    def _feed_lines(self, lines, chunk: int = 5000):
        """Akışı parça parça tüketir; kilit sık bırakılır, satırlar biriktirilmez (bellek sınırlı)."""
        batch = []
        for line in lines:
            batch.append(line)
            if len(batch) >= chunk:
                self._drain(batch)
                batch = []
        if batch:
            self._drain(batch)

    def _drain(self, batch):
        with self.lock:
            for line in batch:
                try:
                    self.view.feed(decode(line))
                    self.lines += 1
                except Exception:  # noqa: BLE001 — görünüm, hot path değil; bozuk satır atlanır
                    continue

    def run(self):
        files = self._files()
        start = max(0, len(files) - self.history_files)
        for p in files[start:-1] if files else []:
            self._feed_lines(GrowingGzipReader(p).read_new())
            self.done.add(p.name)
        self.loading = False
        while True:
            files = self._files()
            pending = [p for p in files if p.name not in self.done]
            if not pending:
                time.sleep(1.0)
                continue
            p = pending[0]
            if self.current != p:
                self.current, self.reader = p, GrowingGzipReader(p)
            before = self.lines
            self._feed_lines(self.reader.read_new())
            if self.lines > before:
                pass
            elif self.reader.finished or len(pending) > 1 and self._closed(p):
                self.done.add(p.name)
            else:
                time.sleep(0.5)

    def _closed(self, p: Path) -> bool:
        m = self.run_dir / "manifest.jsonl"
        return m.exists() and p.name in m.read_text()


class Api:
    def __init__(self, run_dir: Path, ui_dir: Path, history_files: int, auth: AuthConfig | None = None):
        self.run_dir, self.ui_dir = run_dir, ui_dir
        self.auth = auth or AuthConfig(token=os.environ.get("FBOT_UI_TOKEN") or None,
                                       protect_reads=os.environ.get("FBOT_UI_PROTECT_READS", "") == "1")
        rec_cfg = tomllib.loads((ROOT / "config" / "recorder.toml").read_text())
        res_cfg = tomllib.loads((ROOT / "config" / "research.toml").read_text())
        symbols = self._symbols()
        f = res_cfg["features"]; st = res_cfg["states"]
        self.view = LiveView(symbols, W=f["W"], N_short=f["N_short"], N_long=f["N_long"], p_lo=st["p_lo"], p_hi=st["p_hi"])
        self.lock = threading.Lock()
        self.tailer = Tailer(run_dir, self.view, self.lock, history_files)
        self.kill = KillSwitch(ROOT / "data" / "state" / "kill_switch.json")
        self.staleness_s = rec_cfg.get("staleness_s", {})
        self._cache = (0.0, None)

    def _last_run(self) -> dict:
        r = self.run_dir / "runs.jsonl"
        if r.exists():
            lines = [l for l in r.read_text().splitlines() if l.strip()]
            if lines:
                return json.loads(lines[-1])
        return {}

    def _symbols(self) -> list[str]:
        return self._last_run().get("symbols", [])

    def start(self):
        self.tailer.start()

    @staticmethod
    def _read_json(p: Path):
        try:
            return json.loads(p.read_text()) if p.exists() else None
        except ValueError:
            return None

    def _paper(self, run_id: str | None = None) -> dict:
        """Paper/testnet koşusu — ayrı süreç/container; konsol yalnızca SQLite'ı salt okur."""
        try:
            base = Path(self.run_dir).parent
            snap = paper_snapshot(base, run_id=run_id)
            envs = environments(base)
        except Exception as e:  # noqa: BLE001 — konsol paper olmadan da çalışır
            return {"paper": {"error": repr(e)}, "environments": [], "positions": [], "verdicts": [], "fsm": {}, "exit_reasons": {}, "paper_running": False}
        return {"environments": envs,
                "paper": {"run_id": snap["run_id"], "env": snap["env"], "runs": snap["runs"],
                          "metrics": snap["metrics"], "open_count": snap["open_count"]},
                "positions": snap["positions"], "verdicts": snap["verdicts"], "fsm": snap["fsm"],
                "exit_reasons": snap["exit_reasons"], "paper_running": snap["run_id"] is not None}

    def state(self, run_id: str | None = None) -> dict:
        now = time.time()
        if run_id is None and now - self._cache[0] < 1.0 and self._cache[1] is not None:
            return self._cache[1]
        with self.lock:
            snap = self.view.snapshot(time.time_ns())
        run = self._last_run()
        snap["recorder"].update({k: run.get(k) for k in ("run_id", "restart_no", "git_sha", "config_hash", "start_ns")})
        self.kill = KillSwitch(self.kill.path)   # dosyadan taze oku (elle sıfırlama görünsün)
        phases_md = (ROOT / "docs" / "PHASE.md").read_text() if (ROOT / "docs" / "PHASE.md").exists() else ""
        lat_md = (ROOT / "docs" / "latency-baseline.generated.md").read_text() if (ROOT / "docs" / "latency-baseline.generated.md").exists() else ""
        du = shutil.disk_usage(str(self.run_dir))
        rec_size = sum(f["size"] for f in recorder_files(self.run_dir))
        out = {
            "t_ms": int(now * 1000), "mode": "paper", "loading": self.tailer.loading, "tail_lines": self.tailer.lines,
            "kill": {"active": self.kill.active, **{k: v for k, v in self.kill.state.items() if k != "active"}},
            "phases": parse_phase_table(phases_md)[:11],
            "staleness_s": self.staleness_s,
            **snap,
            "recorder_files": recorder_files(self.run_dir)[:8], "recorder_bytes": rec_size, "disk_free_gb": round(du.free / 1e9, 1),
            "research": self._read_json(ROOT / "data" / "research" / "hist-30d" / "report.json"),
            "replay_cmp": self._read_json(ROOT / "data" / "research" / "replay-positions.json"),
            "latency": parse_latency_md(lat_md),
            "config": assemble_config(ROOT / "config"),
            **self._paper(run_id),
        }
        if run_id is None:
            self._cache = (now, out)
        return out


def make_handler(api: Api):
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=str(api.ui_dir), **kw)

        def log_message(self, fmt, *args):  # sessiz
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            ok, why = auth_check(self.command, self.path, dict(self.headers), api.auth)
            if not ok:
                self._json({"error": why}, 401)
            return ok

        def do_GET(self):
            if not self._authorized():
                return
            if self.path.startswith("/api/state"):
                from urllib.parse import parse_qs, urlparse
                run = (parse_qs(urlparse(self.path).query).get("run") or [None])[0]
                return self._json(api.state(run))
            if self.path.startswith("/api/health"):
                return self._json({"ok": True, "loading": api.tailer.loading, "lines": api.tailer.lines})
            if self.path in ("/", ""):
                self.path = "/index.html"
            return super().do_GET()

        def do_POST(self):
            if not self._authorized():
                return
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            if self.path == "/api/kill":
                api.kill = KillSwitch(api.kill.path)
                api.kill.trigger(body.get("reason") or "manual (konsol)", time.time_ns(), git_sha())
                api._cache = (0.0, None)
                return self._json({"active": api.kill.active, **api.kill.state})
            if self.path == "/api/kill/reset":
                api.kill = KillSwitch(api.kill.path)
                api.kill.reset(body.get("note") or "manual reset (konsol)", time.time_ns())
                api._cache = (0.0, None)
                return self._json({"active": api.kill.active, **api.kill.state})
            return self._json({"error": "not found"}, 404)
    return H


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL).decode().strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="data/recordings/rec-72h")
    ap.add_argument("--ui-dir", default="ui")
    ap.add_argument("--bind", default=os.environ.get("FBOT_UI_BIND", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("FBOT_UI_PORT", "8787")))
    ap.add_argument("--history-files", type=int, default=5, help="başlangıçta oynatılacak kapalı dosya sayısı (saat)")
    ap.add_argument("--protect-reads", action="store_true", help="okuma uçlarını da token ile koru")
    a = ap.parse_args(argv)
    token = os.environ.get("FBOT_UI_TOKEN") or None
    api = Api(Path(a.run_dir), Path(a.ui_dir), a.history_files,
              AuthConfig(token=token, protect_reads=a.protect_reads or os.environ.get("FBOT_UI_PROTECT_READS", "") == "1"))
    api.start()
    srv = ThreadingHTTPServer((a.bind, a.port), make_handler(api))
    print(json.dumps({"msg": "konsol", "url": f"http://{a.bind}:{a.port}/", "run_dir": a.run_dir,
                      "yazma_uçları": "token ile açık" if token else "KAPALI (FBOT_UI_TOKEN yok)",
                      "okuma_koruması": bool(api.auth.protect_reads)}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main(sys.argv[1:])
