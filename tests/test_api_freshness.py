"""Veri tazeliği — konsol bayat veriyi güncelmiş gibi göstermemeli (F05)."""
from fbot.api.freshness import assess


def test_loading_is_reported_even_when_data_looks_fresh():
    f = assess(loading=True, tail_lines=1000, last_event_ns=None, now_ns=0, stale_age_s={}, thresholds_s={})
    assert f["status"] == "loading" and f["live"] is False and "geçmiş" in f["reason"]


def test_stale_when_last_event_older_than_threshold():
    now = 100_000_000_000_000
    old = now - 65_000 * 1_000_000_000                       # 18 saat önce
    f = assess(loading=False, tail_lines=5, last_event_ns=old, now_ns=now,
               stale_age_s={"public": 65000.0, "market": 65000.0}, thresholds_s={"public": 30, "market": 30})
    assert f["status"] == "stale" and f["live"] is False
    assert round(f["data_age_s"]) == 65000
    assert set(f["stale_categories"]) == {"public", "market"}


def test_live_when_fresh_and_loaded():
    now = 100_000_000_000_000
    f = assess(loading=False, tail_lines=5, last_event_ns=now - 2_000_000_000, now_ns=now,
               stale_age_s={"public": 2.0}, thresholds_s={"public": 30})
    assert f["status"] == "live" and f["live"] is True and f["stale_categories"] == []


def test_no_data_at_all_is_not_live():
    f = assess(loading=False, tail_lines=0, last_event_ns=None, now_ns=1, stale_age_s={}, thresholds_s={})
    assert f["status"] == "no_data" and f["live"] is False


def test_default_threshold_used_when_category_missing():
    now = 10_000_000_000_000
    f = assess(loading=False, tail_lines=1, last_event_ns=now - 1_000_000_000, now_ns=now,
               stale_age_s={"private": 120.0}, thresholds_s={}, default_threshold_s=30)
    assert f["stale_categories"] == ["private"] and f["status"] == "stale"
