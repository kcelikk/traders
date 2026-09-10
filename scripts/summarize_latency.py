"""Ölçüm çıktısını Markdown özetine çevirir (akış halinde okur, düşük bellek).
Kullanım: python -m scripts.summarize_latency <run_dir>"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from scripts.latency_core import hour_bucket, percentiles


class Acc:
    """Sayısal seri toplayıcı: yalnızca değer listesi tutar, dict tutmaz."""

    def __init__(self):
        self.v: list[float] = []

    def add(self, x):
        if x is not None:
            self.v.append(x)

    def stats(self) -> dict:
        v = self.v
        if not v:
            return {"count": 0, "min": None, "max": None, "mean": None, "p50": None, "p95": None, "p99": None}
        return {"count": len(v), "min": min(v), "max": max(v), "mean": sum(v) / len(v), **percentiles(v)}


def iter_jsonl(path: Path):
    if not path.exists():
        return
    with path.open() as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def fmt(v, nd=1):
    if v is None:
        return "—"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


HDR = "| Seri | n | p50 | p95 | p99 | min | max | ort |\n|---|---|---|---|---|---|---|---|"


def row(label: str, s: dict, nd=1) -> str:
    return f"| {label} | {s['count']} | {fmt(s['p50'], nd)} | {fmt(s['p95'], nd)} | {fmt(s['p99'], nd)} | {fmt(s['min'], nd)} | {fmt(s['max'], nd)} | {fmt(s['mean'], nd)} |"


def collect(path: Path, keys: list[str], group_key: str | None = None):
    """Döndürür: total[key] -> Acc, by_group[(group, key)] -> Acc, by_hour[(hour, key)] -> Acc"""
    total = defaultdict(Acc)
    by_group = defaultdict(Acc)
    by_hour = defaultdict(Acc)
    n = 0
    first = last = None
    for r in iter_jsonl(path):
        n += 1
        w = r["wall_ms"]
        first = w if first is None else first
        last = w
        h = hour_bucket(w)
        g = r.get(group_key) if group_key else None
        for k in keys:
            x = r.get(k)
            total[k].add(x)
            by_hour[(h, k)].add(x)
            if g is not None:
                by_group[(g, k)].add(x)
    return n, first, last, total, by_group, by_hour


def hour_rows(by_hour, key) -> list[str]:
    hours = sorted({h for (h, k) in by_hour if k == key})
    return [row(h, by_hour[(h, key)].stats()) for h in hours]


def main(run_dir: Path):
    out = [f"# Ölçüm özeti — `{run_dir.name}`", ""]
    ev = list(iter_jsonl(run_dir / "events.jsonl"))
    if ev:
        t0, t1 = min(e["wall_ms"] for e in ev), max(e["wall_ms"] for e in ev)
        out.append(f"Süre: {(t1 - t0) / 3600000:.2f} saat ({t0} → {t1} ms epoch)")
        kinds = Counter(e["kind"] for e in ev)
        out.append("Olaylar: " + ", ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
        out.append("")

    n, _, _, ka, _, ka_h = collect(run_dir / "rest_keepalive.jsonl", ["rtt_ms", "skew_ms"])
    _, _, _, nc, _, _ = collect(run_dir / "rest_newconn.jsonl", ["connect_ms", "total_ms"])
    if n:
        out += ["## REST `GET /fapi/v1/time` (ms)", "", HDR]
        out.append(row("keep-alive RTT", ka["rtt_ms"].stats()))
        out.append(row("yeni bağlantı: TCP+TLS connect", nc["connect_ms"].stats()))
        out.append(row("yeni bağlantı: toplam (connect+istek)", nc["total_ms"].stats()))
        out.append(row("clock skew (server − local orta nokta)", ka["skew_ms"].stats()))
        out += ["", "### Keep-alive RTT saat bazında", "", HDR, *hour_rows(ka_h, "rtt_ms")]
        out += ["", "### Clock skew saat bazında", "", HDR, *hour_rows(ka_h, "skew_ms")]

    for name, title in (("ws_public", "/public bookTicker"), ("ws_market", "/market aggTrade + markPrice@1s")):
        n, first, last, tot, byg, byh = collect(run_dir / f"{name}.jsonl", ["lag_E_ms", "lag_T_ms", "parse_us", "bytes"], "stream")
        if not n:
            continue
        out += ["", f"## WS {title} (ms)", "", HDR]
        for st in sorted({g for (g, k) in byg}):
            out.append(row(f"{st}: recv − E", byg[(st, "lag_E_ms")].stats()))
            if byg[(st, "lag_T_ms")].v:
                out.append(row(f"{st}: recv − T", byg[(st, "lag_T_ms")].stats()))
        out.append(row("json.loads süresi (µs)", tot["parse_us"].stats()))
        out.append(row("mesaj boyutu (byte)", tot["bytes"].stats(), 0))
        # hız: örneklemeden bağımsız sayaç dosyası
        per_stream = Counter()
        peak = Counter()
        secs = set()
        for r in iter_jsonl(run_dir / f"{name}_rate.jsonl"):
            per_stream[r["stream"]] += r["n"]
            peak[r["wall_ms"]] += r["n"]
            secs.add(r["wall_ms"])
        if secs:
            span = len(secs)
            out.append("")
            out.append(f"Örneklenen kayıt: {n}. Toplam mesaj (sayaç): " + ", ".join(f"{k}={v}" for k, v in sorted(per_stream.items())))
            out.append("Ortalama hız (msg/s, aktif saniyeler): " + ", ".join(f"{k}={v / span:.2f}" for k, v in sorted(per_stream.items())))
            out.append(f"Tepe saniye (kategori toplamı): {max(peak.values())} msg/s")
        out += ["", f"### {title}: recv − E saat bazında", "", HDR, *hour_rows(byh, "lag_E_ms")]

    n, _, _, api, _, api_h = collect(run_dir / "ws_api.jsonl", ["rtt_ms", "lag_E_ms"])
    if n:
        out += ["", "## WS API `depth` limit=5 (ms)", "", HDR]
        out.append(row("istek → cevap RTT", api["rtt_ms"].stats()))
        out.append(row("cevap alımı − E", api["lag_E_ms"].stats()))
        out += ["", "### WS API RTT saat bazında", "", HDR, *hour_rows(api_h, "rtt_ms")]
        last = None
        for r in iter_jsonl(run_dir / "ws_api.jsonl"):
            last = r
        if last and last.get("rateLimits"):
            out += ["", "Son `rateLimits`: `" + json.dumps(last["rateLimits"]) + "`"]

    errs = [e for e in ev if "error" in e["kind"] or "disconnect" in e["kind"] or "mismatch" in e["kind"]]
    if errs:
        out += ["", f"## Hata / kopma olayları ({len(errs)}; ilk 20)", ""]
        for e in errs[:20]:
            out.append(f"- {e['wall_ms']} {e['kind']} {e.get('err', '')}")
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
