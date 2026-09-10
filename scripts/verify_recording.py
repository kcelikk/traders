"""Kayıt bütünlük raporu (Faz 1 kapısı). Kullanım: python -m scripts.verify_recording data/recordings/<run_id>"""
from __future__ import annotations

import gzip
import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from fbot.events import decode
from fbot.integrity import SeqChecker, StreamChecker
from scripts.latency_core import hour_bucket, percentiles


def read_gz_lines(path: Path):
    """Kesik gzip'te okunabilen kısmı döndürür; kesikse bayrak."""
    truncated = False
    lines = []
    try:
        with gzip.open(path, "rb") as f:
            for line in f:
                if line.endswith(b"\n"):
                    lines.append(line)
                else:
                    truncated = True
    except (EOFError, OSError):
        truncated = True
    return lines, truncated


def main(run_dir: Path):
    manifest = [json.loads(l) for l in (run_dir / "manifest.jsonl").read_text().splitlines() if l.strip()] if (run_dir / "manifest.jsonl").exists() else []
    runs = [json.loads(l) for l in (run_dir / "runs.jsonl").read_text().splitlines() if l.strip()] if (run_dir / "runs.jsonl").exists() else []
    in_manifest = {m["file"] for m in manifest}
    all_files = sorted(p.name for p in run_dir.glob("events-*.jsonl.gz"))
    open_files = [f for f in all_files if f not in in_manifest]

    seqc, strc = SeqChecker(), StreamChecker()
    ctrl = Counter()
    sha_bad, truncated = [], []
    first_ns = last_ns = None
    prev_ns = None
    max_gap_s = 0.0
    max_gap_at = None
    per_hour = Counter()
    lag_p99, lag_max, queue_max, dropped_last = [], 0.0, 0, 0
    stale_events, reconnects = [], []
    snapshot_ok = snapshot_bad = 0
    total_bytes = 0

    for name in all_files:
        path = run_dir / name
        lines, trunc = read_gz_lines(path)
        if trunc:
            truncated.append(name)
        m = next((x for x in manifest if x["file"] == name), None)
        if m is not None:
            h = hashlib.sha256()
            for l in lines:
                h.update(l)
            if h.hexdigest() != m["sha256"] or len(lines) != m["count"]:
                sha_bad.append(name)
        total_bytes += path.stat().st_size
        for l in lines:
            ev = decode(l)
            seqc.feed(ev.seq)
            if first_ns is None:
                first_ns = ev.recv_ns
            last_ns = ev.recv_ns
            if prev_ns is not None:
                gap = (ev.recv_ns - prev_ns) / 1e9
                if gap > max_gap_s:
                    max_gap_s, max_gap_at = gap, ev.recv_ns
            prev_ns = ev.recv_ns
            per_hour[hour_bucket(ev.recv_ns // 10**6)] += 1
            if ev.cat == "ctrl":
                ctrl[ev.stream] += 1
                info = json.loads(ev.raw)
                if ev.stream == "connect":
                    strc.reset(info["cat"])
                    reconnects.append((ev.recv_ns, info["cat"], info.get("n")))
                elif ev.stream == "stale":
                    stale_events.append((ev.recv_ns, info["cat"], info["age_s"]))
                elif ev.stream == "stats":
                    lag_p99.append(info["loop_lag_ms"]["p99"]); lag_max = max(lag_max, info["loop_lag_ms"]["max"])
                    queue_max = max(queue_max, info["queue"]); dropped_last = info["dropped"]
                elif ev.stream == "snapshot":
                    if info.get("status") == 200:
                        snapshot_ok += 1
                    else:
                        snapshot_bad += 1
            else:
                strc.feed(ev.stream, ev.raw)

    sr = seqc.report()
    hours = (last_ns - first_ns) / 3.6e12 if first_ns else 0
    out = [f"# Kayıt doğrulama — `{run_dir.name}`", ""]
    out.append(f"Kapsam: **{hours:.2f} saat** ({first_ns} → {last_ns} ns). Başlangıç sayısı: {len(runs)}. Dosya: {len(all_files)} (manifestte {len(in_manifest)}, açık {len(open_files)}). Disk: {total_bytes/1e6:.1f} MB gzip.")
    out.append("")
    out.append("## Kapı kriterleri")
    out.append("")
    out.append("| Kriter | Değer | Durum |")
    out.append("|---|---|---|")
    out.append(f"| seq boşluğu | {sr['gaps']} (eksik {sr['missing']}) | {'OK' if sr['gaps'] == 0 else 'HATA'} |")
    out.append(f"| seq tekrarı | {sr['dups']} | {'OK' if sr['dups'] == 0 else 'HATA'} |")
    out.append(f"| SHA-256 / sayım uyuşmazlığı | {len(sha_bad)} | {'OK' if not sha_bad else 'HATA: ' + ', '.join(sha_bad)} |")
    out.append(f"| kesik gzip | {len(truncated)} | {'OK' if not truncated else 'UYARI (açık dosya olabilir): ' + ', '.join(truncated)} |")
    out.append(f"| kuyruk taşması (dropped) | {dropped_last} | {'OK' if dropped_last == 0 else 'HATA'} |")
    out.append(f"| süre ≥ 72 saat | {hours:.2f} | {'OK' if hours >= 72 else 'HENÜZ DEĞİL'} |")
    out.append("")
    out.append("## Olaylar")
    out.append("")
    out.append(f"Toplam olay: {sr['count']}. Kontrol olayları: " + ", ".join(f"{k}={v}" for k, v in sorted(ctrl.items())))
    out.append(f"En büyük olaysız aralık: {max_gap_s:.2f} s" + (f" (bitiş {max_gap_at})" if max_gap_at else ""))
    out.append(f"Bağlantı kurulumları: {len(reconnects)}; bayatlık olayları: {len(stale_events)}; snapshot OK/hata: {snapshot_ok}/{snapshot_bad}")
    if lag_p99:
        lp = percentiles(lag_p99)
        out.append(f"Loop lag (10 s pencerelerinin p99'ları): p50={lp['p50']:.2f} ms, p99={lp['p99']:.2f} ms; mutlak maks {lag_max:.2f} ms; kuyruk maks {queue_max}")
    out.append("")
    out.append("## Stream bütünlüğü")
    out.append("")
    out.append("| Stream | olay | zincir kopuşu | E geriye gidiş | parse hatası |")
    out.append("|---|---|---|---|---|")
    for s, r in sorted(strc.report().items()):
        out.append(f"| {s} | {r['count']} | {r['breaks']} | {r['E_regressions']} | {r['parse_errors']} |")
    out.append("")
    out.append("## Saat bazında olay sayısı")
    out.append("")
    out.append("| saat (UTC) | olay |")
    out.append("|---|---|")
    for h in sorted(per_hour):
        out.append(f"| {h} | {per_hour[h]} |")
    if reconnects:
        out.append("")
        out.append("## Bağlantı olayları (ilk 30)")
        out.append("")
        for ns, cat, n in reconnects[:30]:
            out.append(f"- {ns} {cat} connect #{n}")
    if stale_events:
        out.append("")
        out.append("## Bayatlık olayları (ilk 30)")
        out.append("")
        for ns, cat, age in stale_events[:30]:
            out.append(f"- {ns} {cat} age={age}s")
    print("\n".join(out))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
