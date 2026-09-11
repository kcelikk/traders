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


def bootstrap_ci_fast(values: list[float], n_boot: int, seed: int, alpha: float) -> tuple[float, float]:
    """`bootstrap_ci` ile aynı tahmin edici, C seviyesinde çekilişle ~10x hızlı.

    Çekiliş **sırası** farklı olduğu için sayılar birebir aynı çıkmaz (örnekleme gürültüsü kadar
    fark eder). Faz 3 raporunun hash'i bozulmasın diye eski fonksiyon değiştirilmedi; bu sürüm
    yalnızca tarama gibi çok sayıda aralık hesaplayan yerlerde kullanılır. Seed'lidir (Rule Zero #5).
    """
    n = len(values)
    if n == 0:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    choices = rng.choices
    means = sorted(sum(choices(values, k=n)) / n for _ in range(n_boot))
    lo = means[int(alpha / 2 * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return (lo, hi)
