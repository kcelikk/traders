from fbot.research.stats import bootstrap_ci, summarize


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
