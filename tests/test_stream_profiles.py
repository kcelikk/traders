"""Rol bazlı stream profilleri (Gate 1): her süreç yalnız kullandığı veriyi çeker.

Testnet dolum simülatörü kullanmaz (`_NullSim`), ama bugüne kadar tam L2 defteri kuruyor ve
depth maliyetini bedavaya ödüyordu.
"""
import pytest

from fbot.config import ConfigError, STREAM_PROFILES, apply_profile, load_recorder_config, stream_kind
from fbot.paper.config import PaperConfigError, load_paper_config

ALL = ["{s}@bookTicker", "{s}@depth@100ms", "{s}@aggTrade", "{s}@markPrice@1s", "{s}@forceOrder"]


def test_recorder_profile_keeps_everything():
    assert apply_profile(ALL, "recorder") == ALL


def test_trader_paper_drops_only_force_order():
    assert apply_profile(ALL, "trader_paper") == ["{s}@bookTicker", "{s}@depth@100ms", "{s}@aggTrade", "{s}@markPrice@1s"]


def test_trader_testnet_drops_depth_too():
    assert apply_profile(ALL, "trader_testnet") == ["{s}@bookTicker", "{s}@aggTrade", "{s}@markPrice@1s"]


def test_unknown_profile_is_an_error():
    with pytest.raises(ConfigError, match="profile"):
        apply_profile(ALL, "hepsi")


def test_unknown_stream_template_is_an_error_not_silently_dropped():
    with pytest.raises(ConfigError, match="bilinmeyen stream"):
        stream_kind("{s}@kline_1m")


def test_config_files_declare_their_role(repo_root):
    assert load_recorder_config(repo_root / "config/recorder.toml")[0].profile == "recorder"
    assert load_paper_config(repo_root / "config/paper.toml")[0].recorder.profile == "trader_paper"
    assert load_paper_config(repo_root / "config/testnet.toml")[0].recorder.profile == "trader_testnet"


def test_paper_without_depth_is_fail_closed(tmp_path, repo_root):
    """Depth'siz paper profili dolum simülasyonunu sessizce bozar; yükleme reddedilmeli."""
    src = (repo_root / "config/paper.toml").read_text()
    bad = src.replace('public = ["{s}@bookTicker", "{s}@depth@100ms"]', 'public = ["{s}@bookTicker"]')
    f = tmp_path / "paper-nodepth.toml"
    f.write_text(bad)
    with pytest.raises(PaperConfigError, match="depth"):
        load_paper_config(f)


def test_every_profile_is_a_subset_of_recorder():
    for name, kinds in STREAM_PROFILES.items():
        assert kinds <= STREAM_PROFILES["recorder"], name
