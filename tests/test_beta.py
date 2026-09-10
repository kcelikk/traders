"""BTC-beta: sembolün 1 dk log getirisinin BTC'ye rolling regresyon eğimi (Faz 5 K9). Saf."""
import math

from fbot.research.beta import beta_series, rolling_beta


def test_perfect_correlation_gives_one():
    btc = [0.001 * (i % 5 - 2) for i in range(60)]
    assert abs(rolling_beta(btc, btc) - 1.0) < 1e-12


def test_double_amplitude_gives_two():
    btc = [0.001 * (i % 7 - 3) for i in range(60)]
    alt = [2 * x for x in btc]
    assert abs(rolling_beta(btc, alt) - 2.0) < 1e-9


def test_uncorrelated_is_near_zero():
    btc = [0.001 * math.sin(i) for i in range(200)]
    alt = [0.001 * math.cos(i) for i in range(200)]
    assert abs(rolling_beta(btc, alt)) < 0.2


def test_zero_variance_returns_none():
    assert rolling_beta([0.0] * 30, [0.001] * 30) is None
    assert rolling_beta([], []) is None
    assert rolling_beta([0.1, 0.2], [0.1, 0.2], min_n=10) is None


def test_beta_series_aligns_on_timestamps_and_is_rolling():
    """Ortak zaman damgası olmayan barlar atlanır; pencere kayar."""
    btc = [{"start_ms": i * 60000, "close": 100 * (1 + 0.001 * (i % 5 - 2))} for i in range(100)]
    alt = [{"start_ms": i * 60000, "close": 50 * (1 + 0.002 * (i % 5 - 2))} for i in range(100) if i != 7]
    out = beta_series(btc, alt, window=30)
    assert out and all(b["n"] <= 30 for b in out)
    assert abs(out[-1]["beta"] - 2.0) < 0.05
    assert all(b["t_ms"] % 60000 == 0 for b in out)
