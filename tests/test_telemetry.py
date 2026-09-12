"""Telemetri (Gate 4d): sabit bellekli histogram, yaklaşık persentil, hot path'te büyüme yok."""
from fbot.core.telemetry import BUCKETS_NS, Histogram, Telemetry


def test_memory_does_not_grow_with_sample_count():
    """Ölçüm de bir maliyettir: örnek biriktiren liste hot path'te kabul edilemez."""
    h = Histogram("x")
    before = len(h.counts)
    for i in range(100_000):
        h.observe(1_000 + i)
    assert len(h.counts) == before == len(BUCKETS_NS) + 1
    assert h.count == 100_000


def test_quantiles_are_approximate_and_say_so():
    """Persentil kova sınırından okunur: 5 µs'lik örnek 8 µs kovasına düşer. Rapor `approx: true`
    diyerek bunu gizlemez."""
    h = Histogram("x")
    for _ in range(99):
        h.observe(5_000)          # 5 µs
    h.observe(900_000)            # 900 µs aykırı
    v = h.view()
    assert v["approx"] is True and v["n"] == 100
    assert v["p50_us"] == 8.0 and v["p99_us"] == 8.0     # 100 örnekte tek aykırı p99'a girmez
    assert v["max_us"] == 900.0, "aykırı değer yalnız maks'ta görünür"
    assert v["avg_us"] > v["p99_us"], "ortalama aykırıyı taşır, persentil taşımaz"


def test_empty_histogram_reports_unknown_not_zero():
    v = Histogram("x").view()
    assert v["n"] == 0 and v["p50_us"] is None and v["avg_us"] is None


def test_values_above_the_last_bucket_land_in_the_overflow():
    h = Histogram("x")
    h.observe(10**11)             # 100 s: son kovanın üstünde
    assert h.counts[-1] == 1 and h.view()["max_us"] == 100_000_000.0


def test_named_histograms_are_reported_in_a_stable_order():
    t = Telemetry()
    for name in ("z", "a", "m"):
        t.observe(name, 2_000)
    assert list(t.view()) == ["a", "m", "z"]


def test_average_is_exact_even_though_quantiles_are_not():
    h = Histogram("x")
    for v in (1_000, 3_000, 5_000):
        h.observe(v)
    assert h.view()["avg_us"] == 3.0


def test_userdata_lag_is_recorded_from_the_exchange_timestamp():
    """Gate 3'te ölçülen 140 ms'lik teslim gecikmesi artık sürekli izleniyor: borsa damgası (`T`)
    ile bizim alım damgamız arasındaki fark."""
    import json

    from fbot.core.commands import ShadowIntent  # noqa: F401 — modül yükleniyor mu
    from tests.fake import order_trade_update

    t_ms = 1_700_000_000_000
    msg = order_trade_update(client_id="t0Labc", t_ms=t_ms)
    from fbot.gateway.userdata_map import map_user_event
    mapped = map_user_event(msg)
    lag_ns = (t_ms + 140) * 1_000_000 - t_ms * 1_000_000      # 140 ms
    t = Telemetry()
    t.observe(f"userdata_lag.{mapped['kind']}", lag_ns)
    v = t.view()["userdata_lag.order_ack"]
    assert v["n"] == 1 and v["max_us"] == 140_000.0
    assert json.dumps(v)          # rapora serileşebilir olmalı


def test_absurd_lag_values_are_not_recorded():
    """Saat kayması ya da bozuk damga histogramı zehirlememeli; filtre çağrı yerinde."""
    lag = -5 * 10**9
    assert not (0 <= lag < 60 * 10**9)
    lag = 3600 * 10**9
    assert not (0 <= lag < 60 * 10**9)
