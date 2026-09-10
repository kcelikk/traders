"""Seed'li bootstrap ve özet. Rastlantı yalnızca burada ve seed'lidir (Rule Zero #5)."""
from __future__ import annotations

import random


def summarize(values: list[float]) -> dict:
    n = len(values)
    if n == 0:
        return {"n": 0, "mean": None, "median": None, "win_rate": None, "std": None}
    s = sorted(values)
    mean = sum(values) / n
    median = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    var = sum((v - mean) ** 2 for v in values) / (n - 1) if n > 1 else 0.0
    return {"n": n, "mean": mean, "median": median, "win_rate": sum(1 for v in values if v > 0) / n, "std": var ** 0.5}


def bootstrap_ci(values: list[float], n_boot: int, seed: int, alpha: float) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        acc = 0.0
        for _ in range(n):
            acc += values[rng.randrange(n)]
        means.append(acc / n)
    means.sort()
    lo = means[int(alpha / 2 * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi)
