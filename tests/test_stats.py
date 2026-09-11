from fbot.research.stats import bootstrap_ci, bootstrap_ci_fast, summarize


def test_bootstrap_is_seeded_and_brackets_mean():
    v = [0.1, -0.2, 0.3, 0.05, -0.1, 0.2, 0.0, 0.15, -0.05, 0.1]
    a = bootstrap_ci(v, n_boot=500, seed=7, alpha=0.05)
    b = bootstrap_ci(v, n_boot=500, seed=7, alpha=0.05)
    assert a == b
    assert a[0] <= sum(v) / len(v) <= a[1]
    assert bootstrap_ci(v, n_boot=500, seed=8, alpha=0.05) != a


def test_summarize_fields():
    s = summarize([1.0, -1.0, 2.0])
    assert s["n"] == 3 and s["mean"] == 2 / 3 and s["median"] == 1.0 and s["win_rate"] == 2 / 3
    assert summarize([])["n"] == 0


def test_fast_bootstrap_matches_the_slow_one_within_sampling_noise():
    """Hızlı sürüm aynı tahmin ediciyi kullanır; yalnızca çekiliş sırası farklıdır.
    Faz 3 raporunun hash'i bozulmasın diye eski fonksiyon değiştirilmedi."""
    import random
    rng = random.Random(7)
    vals = [rng.gauss(0.05, 1.0) for _ in range(3000)]
    lo_s, hi_s = bootstrap_ci(vals, 800, seed=3, alpha=0.05)
    lo_f, hi_f = bootstrap_ci_fast(vals, 800, seed=3, alpha=0.05)
    width = hi_s - lo_s
    assert abs(lo_f - lo_s) < width * 0.2 and abs(hi_f - hi_s) < width * 0.2


def test_fast_bootstrap_is_seeded_and_repeatable():
    vals = [0.1, -0.2, 0.3, 0.4, -0.5] * 40
    a = bootstrap_ci_fast(vals, 200, seed=11, alpha=0.05)
    b = bootstrap_ci_fast(vals, 200, seed=11, alpha=0.05)
    c = bootstrap_ci_fast(vals, 200, seed=12, alpha=0.05)
    assert a == b and a != c


def test_fast_bootstrap_on_empty_input():
    lo, hi = bootstrap_ci_fast([], 100, seed=1, alpha=0.05)
    assert lo != lo and hi != hi          # NaN
