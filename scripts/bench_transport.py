"""Gate 2.1 ölçümü: legacy (istek başına bağlantı) vs kalıcı havuz. Gerçek testnet'e istek atar.

İmzalı **okuma** çağrısı kullanır (`/fapi/v2/balance`): emir göndermez, hesapta iz bırakmaz, ama
TLS el sıkışması ve RTT açısından emir yoluyla aynı yolu izler. Emir POST'unun RTT'si ayrıca
ölçülmek istenirse `scripts/verify_exchange_behavior.py` gerçek emir gönderir.

Kullanım: PYTHONPATH=. python -m scripts.bench_transport --n 30
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from fbot.gateway.credfile import read_testnet_state, testnet_paths
from fbot.gateway.http_pool import HTTPPool
from fbot.gateway.testnet import _HOST, TestnetClient, _http

ROOT = Path(__file__).resolve().parents[1]


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    s = sorted(xs)
    return round(s[min(len(s) - 1, int(q * (len(s) - 1) + 0.5))], 1)


def measure(client: TestnetClient, n: int) -> dict:
    rtt: list[float] = []
    errors = 0
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            client.balance(int(time.time() * 1000))
        except Exception:  # noqa: BLE001 — ölçümde hata da bir sonuçtur
            errors += 1
        rtt.append((time.perf_counter() - t0) * 1000)
    return {"n": n, "p50_ms": pct(rtt, 0.5), "p95_ms": pct(rtt, 0.95), "p99_ms": pct(rtt, 0.99),
            "min_ms": round(min(rtt), 1), "max_ms": round(max(rtt), 1), "errors": errors}


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    state = read_testnet_state(testnet_paths(ROOT))
    if state.creds is None:
        raise SystemExit(f"testnet anahtarı yok: {state.reason}")
    creds = state.creds

    legacy = measure(TestnetClient(creds, http=_http), a.n)
    pool = HTTPPool(_HOST, connect_timeout_s=2.0, read_timeout_s=5.0)
    pooled = measure(TestnetClient(creds, http=pool.as_callable()), a.n)
    out = {"endpoint": "/fapi/v2/balance (imzalı okuma)", "legacy": legacy, "persistent": pooled,
           "pool_stats": dict(pool.stats),
           "tls_handshakes": {"legacy": a.n, "persistent": pool.stats["connects"]}}
    pool.close()
    text = json.dumps(out, ensure_ascii=False, indent=1)
    print(text)
    if a.out:
        Path(a.out).write_text(text + "\n")


if __name__ == "__main__":
    main(sys.argv[1:])
