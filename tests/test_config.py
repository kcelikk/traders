import pytest

from fbot.config import load_recorder_config, ConfigError

GOOD = """
[run]
out_dir = "data/recordings"
rotate_minutes = 60
snapshot_interval_s = 600

[universe]
mode = "top"
top_n = 10
exclude_bases = ["USDC", "FDUSD"]

[streams]
public = ["{s}@bookTicker", "{s}@depth@100ms"]
market = ["{s}@aggTrade", "{s}@markPrice@1s", "{s}@forceOrder"]

[staleness_s]
public = 30
market = 30

[reconnect]
backoff_initial_s = 1.0
backoff_max_s = 30.0
"""


def test_load_good_config(tmp_path):
    p = tmp_path / "r.toml"; p.write_text(GOOD)
    cfg, h = load_recorder_config(p)
    assert cfg.top_n == 10 and cfg.mode == "top"
    assert cfg.public_streams == ["{s}@bookTicker", "{s}@depth@100ms"]
    assert cfg.staleness_s["market"] == 30
    assert len(h) == 12
    # hash içerikten türer: aynı içerik aynı hash
    assert load_recorder_config(p)[1] == h


def test_hash_changes_with_content(tmp_path):
    p = tmp_path / "r.toml"; p.write_text(GOOD)
    _, h1 = load_recorder_config(p)
    p.write_text(GOOD.replace("top_n = 10", "top_n = 5"))
    _, h2 = load_recorder_config(p)
    assert h1 != h2


def test_missing_section_is_error(tmp_path):
    p = tmp_path / "r.toml"; p.write_text(GOOD.replace("[staleness_s]", "[stale]"))
    with pytest.raises(ConfigError):
        load_recorder_config(p)


def test_list_mode_requires_symbols(tmp_path):
    p = tmp_path / "r.toml"; p.write_text(GOOD.replace('mode = "top"', 'mode = "list"'))
    with pytest.raises(ConfigError):
        load_recorder_config(p)


def test_tick_ms_default_and_override(tmp_path):
    p = tmp_path / "r.toml"; p.write_text(GOOD)
    cfg, _ = load_recorder_config(p)
    assert cfg.tick_ms == 1000
    p.write_text(GOOD.replace("[run]", "[run]\ntick_ms = 250"))
    assert load_recorder_config(p)[0].tick_ms == 250
