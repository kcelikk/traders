"""Rate limiter (Faz 9): iki ayrı sayaç, header'dan gerçek değerle senkron, 429 geri çekilme, 418 kill."""
from fbot.core.rate_limit import Limits, RateLimiter


def test_two_independent_counters():
    r = RateLimiter(Limits(weight_1m=2400, orders_10s=300, orders_1m=1200))
    assert r.allow_order(now_ms=0) and r.allow_weight(1, now_ms=0)
    for i in range(300):
        r.on_order(now_ms=i)
    assert r.remaining(0)["orders_10s"] == 0
    assert not r.allow_order(now_ms=5)          # 10 s sayacı doldu
    assert r.allow_weight(100, now_ms=5)        # ağırlık sayacı ayrı, etkilenmez


def test_windows_slide():
    r = RateLimiter(Limits(weight_1m=10, orders_10s=2, orders_1m=100))
    r.on_order(0); r.on_order(1)
    assert not r.allow_order(2)
    assert r.allow_order(10_001)                # 10 s geçti
    r.on_weight(10, 0)
    assert not r.allow_weight(1, 100)
    assert r.allow_weight(1, 60_001)


def test_header_sync_is_authoritative():
    """Tahmini sayaç yetmez: header'dan gelen gerçek değer üzerine yazar (prompt 4.4)."""
    r = RateLimiter(Limits(weight_1m=2400, orders_10s=300, orders_1m=1200))
    r.on_order(0)
    r.sync_headers({"x-mbx-used-weight-1m": "2350", "x-mbx-order-count-10s": "295", "x-mbx-order-count-1m": "40"}, now_ms=0)
    rem = r.remaining(0)
    assert rem["weight_1m"] == 50 and rem["orders_10s"] == 5 and rem["orders_1m"] == 1160
    assert r.allow_order(0)
    r.sync_headers({"x-mbx-order-count-10s": "300"}, now_ms=0)
    assert not r.allow_order(0)


def test_ws_rate_limits_payload_sync():
    r = RateLimiter(Limits(weight_1m=2400, orders_10s=300, orders_1m=1200))
    r.sync_ws([{"rateLimitType": "ORDERS", "interval": "SECOND", "intervalNum": 10, "limit": 300, "count": 299},
               {"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 2400, "count": 12}], now_ms=0)
    assert r.remaining(0)["orders_10s"] == 1 and r.remaining(0)["weight_1m"] == 2388


def test_429_backoff_and_418_kill():
    r = RateLimiter(Limits(weight_1m=2400, orders_10s=300, orders_1m=1200), backoff_ms=5000)
    assert r.on_response(429, now_ms=1000) == "backoff"
    assert not r.allow_order(2000) and not r.allow_weight(1, 2000)
    assert r.allow_order(6001)
    assert r.on_response(418, now_ms=7000) == "kill_switch"
    assert r.banned and not r.allow_order(10**9)


def test_reserve_keeps_room_for_protection_orders():
    r = RateLimiter(Limits(weight_1m=2400, orders_10s=10, orders_1m=1200), reserve_orders=3)
    for i in range(7):
        r.on_order(i)
    assert not r.allow_order(8, entry=True)     # giriş için yer yok (rezerv korunur)
    assert r.allow_order(8, entry=False)        # koruma/çıkış emri rezervi kullanabilir


def test_429_backoff_uses_retry_after_when_the_exchange_sends_it():
    """Sabit 10 s beklemek, borsa 60 s dediğinde yeni bir 429 üretir."""
    r = RateLimiter(Limits(weight_1m=6000, orders_10s=300, orders_1m=1200), backoff_ms=10_000)
    assert r.on_response(429, now_ms=1_000, headers={"Retry-After": "60"}) == "backoff"
    assert r.backoff_until_ms == 1_000 + 60_000
    assert not r.allow_order(now_ms=30_000)
    assert r.allow_order(now_ms=61_001)


def test_429_without_the_header_falls_back_to_the_configured_backoff():
    r = RateLimiter(Limits(weight_1m=6000, orders_10s=300, orders_1m=1200), backoff_ms=10_000)
    r.on_response(429, now_ms=0, headers={})
    assert r.backoff_until_ms == 10_000


def test_unreadable_retry_after_does_not_crash_the_limiter():
    r = RateLimiter(Limits(weight_1m=6000, orders_10s=300, orders_1m=1200), backoff_ms=10_000)
    r.on_response(429, now_ms=0, headers={"retry-after": "yarın"})
    assert r.backoff_until_ms == 10_000


def test_418_bans_and_also_backs_off():
    r = RateLimiter(Limits(weight_1m=6000, orders_10s=300, orders_1m=1200), backoff_ms=10_000)
    assert r.on_response(418, now_ms=0, headers={"Retry-After": "120"}) == "kill_switch"
    assert r.banned and r.backoff_until_ms == 120_000
    assert not r.allow_order(now_ms=10**9), "ban elle sıfırlanmadan açılmaz"


def test_limits_are_read_from_exchange_info_not_hard_coded():
    """2026-09-12 ölçümü: mainnet REQUEST_WEIGHT 2400/dk, testnet 6000/dk. Sabit yazmak,
    mainnet'te 2,5 kat fazla bütçe olduğunu sanmak demekti."""
    from fbot.core.rate_limit import limits_from_exchange_info

    payload = {"rateLimits": [{"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE", "intervalNum": 1, "limit": 2400},
                              {"rateLimitType": "ORDERS", "interval": "SECOND", "intervalNum": 10, "limit": 300},
                              {"rateLimitType": "ORDERS", "interval": "MINUTE", "intervalNum": 1, "limit": 1200}]}
    lim = limits_from_exchange_info(payload)
    assert (lim.weight_1m, lim.orders_10s, lim.orders_1m) == (2400, 300, 1200)


def test_missing_limits_fall_back_to_the_conservative_value():
    """Borsanın söylemediği limiti yukarı yuvarlamak 429 üretmenin en kısa yoludur."""
    from fbot.core.rate_limit import CONSERVATIVE, limits_from_exchange_info

    lim = limits_from_exchange_info({"rateLimits": []})
    assert lim == CONSERVATIVE and CONSERVATIVE.weight_1m == 2400
    assert limits_from_exchange_info({}) == CONSERVATIVE
    assert limits_from_exchange_info({"rateLimits": [{"rateLimitType": "REQUEST_WEIGHT", "interval": "MINUTE",
                                                      "intervalNum": 1, "limit": "abc"}]}).weight_1m == 2400


def test_client_without_explicit_limits_uses_the_conservative_default():
    from fbot.gateway.signing import Credentials
    from fbot.gateway.testnet import TestnetClient

    c = TestnetClient(Credentials(api_key="K", api_secret="S"))
    assert c.limiter.w.limit == 2400, "limit verilmediyse düşük olan varsayılır"
