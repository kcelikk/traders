"""API anahtarı yönetimi: yalnızca yazma, asla okuma; .env atomik ve 600; gizli anahtar hiçbir yanıtta yok."""
import os
import stat

import pytest

from fbot.api.keys import KeyError_, key_status, write_keys


def test_status_masks_and_never_returns_secret(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FBOT_TESTNET_ARMED=2026-09-10\nBINANCE_TESTNET_API_KEY=ABCDEFGH12345678\nBINANCE_TESTNET_API_SECRET=TOPSECRET\n")
    st = key_status(env)
    assert st["testnet"]["armed"] is True and st["testnet"]["key_set"] is True and st["testnet"]["secret_set"] is True
    assert st["testnet"]["masked"].endswith("5678")
    blob = repr(st)
    assert "TOPSECRET" not in blob and "ABCDEFGH12345678" not in blob


def test_status_on_missing_file(tmp_path):
    st = key_status(tmp_path / "yok.env")
    assert st["testnet"]["key_set"] is False and st["live"]["key_set"] is False and st["testnet"]["armed"] is False


def test_write_creates_600_file_and_preserves_other_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FBOT_MODE=paper\nBAŞKA=deger\n")
    write_keys(env, "testnet", {"key": "K" * 64, "secret": "S" * 64, "armed": "2026-09-10"})
    txt = env.read_text()
    assert "FBOT_MODE=paper" in txt and "BAŞKA=deger" in txt
    assert f"BINANCE_TESTNET_API_KEY={'K' * 64}" in txt and f"BINANCE_TESTNET_API_SECRET={'S' * 64}" in txt
    assert "FBOT_TESTNET_ARMED=2026-09-10" in txt
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o600


def test_write_updates_existing_values(tmp_path):
    env = tmp_path / ".env"
    write_keys(env, "testnet", {"key": "K" * 64, "secret": "S" * 64, "armed": "1"})
    write_keys(env, "testnet", {"key": "N" * 64, "secret": "M" * 64, "armed": "1"})
    txt = env.read_text()
    assert txt.count("BINANCE_TESTNET_API_KEY=") == 1 and "N" * 64 in txt and "K" * 64 not in txt


def test_disarm_clears_flag_but_keeps_key(tmp_path):
    env = tmp_path / ".env"
    write_keys(env, "testnet", {"key": "K" * 64, "secret": "S" * 64, "armed": "1"})
    write_keys(env, "testnet", {"armed": ""})
    txt = env.read_text()
    assert "FBOT_TESTNET_ARMED=\n" in txt and f"BINANCE_TESTNET_API_KEY={'K' * 64}" in txt
    assert key_status(env)["testnet"]["armed"] is False


def test_live_env_uses_different_variable_names(tmp_path):
    env = tmp_path / ".env"
    write_keys(env, "live", {"key": "L" * 64, "secret": "X" * 64})
    txt = env.read_text()
    assert f"BINANCE_API_KEY={'L' * 64}" in txt and f"BINANCE_API_SECRET={'X' * 64}" in txt
    assert "BINANCE_TESTNET_API_KEY" not in txt


def test_unknown_env_and_bad_values_rejected(tmp_path):
    env = tmp_path / ".env"
    with pytest.raises(KeyError_):
        write_keys(env, "mainnet-prod", {"key": "K" * 64})
    with pytest.raises(KeyError_, match="satır sonu"):
        write_keys(env, "testnet", {"key": "K" * 30 + "\nBINANCE_API_KEY=hack"})
    with pytest.raises(KeyError_, match="çok kısa"):
        write_keys(env, "testnet", {"key": "abc"})


def test_live_requires_server_side_gate(tmp_path, monkeypatch):
    """Mainnet anahtarı yalnızca sunucuda açılan kapı ile yazılabilir (web formu tek başına yetmez)."""
    env = tmp_path / ".env"
    monkeypatch.delenv("FBOT_LIVE_KEYS_ALLOWED", raising=False)
    with pytest.raises(KeyError_, match="FBOT_LIVE_KEYS_ALLOWED"):
        write_keys(env, "live", {"armed": "1"}, require_gate=True)
    monkeypatch.setenv("FBOT_LIVE_KEYS_ALLOWED", "1")
    write_keys(env, "live", {"armed": "1"}, require_gate=True)
