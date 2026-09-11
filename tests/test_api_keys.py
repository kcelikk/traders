"""API anahtarı yönetimi: yalnızca yazma, asla okuma; dosyalar atomik ve 600; gizli anahtar hiçbir yanıtta yok.

Ortam başına ayrı dosya: testnet anahtarı `data/state/testnet/credentials.env`, mainnet `.env`.
Testnet container'ı yalnızca kendi dosyasını görür, mainnet anahtarına erişemez.
"""
import os
import stat

import pytest

from fbot.api.keys import KeyError_, key_status, write_keys


def test_status_masks_and_never_returns_secret(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FBOT_TESTNET_ARMED=2026-09-10\nBINANCE_TESTNET_API_KEY=ABCDEFGH12345678\nBINANCE_TESTNET_API_SECRET=TOPSECRET\n")
    st = key_status(tmp_path)
    assert st["testnet"]["armed"] is True and st["testnet"]["key_set"] is True and st["testnet"]["secret_set"] is True
    assert st["testnet"]["masked"].endswith("5678")
    blob = repr(st)
    assert "TOPSECRET" not in blob and "ABCDEFGH12345678" not in blob


def test_status_on_missing_file(tmp_path):
    st = key_status(tmp_path / "bos")
    assert st["testnet"]["key_set"] is False and st["live"]["key_set"] is False and st["testnet"]["armed"] is False


def test_write_creates_600_file_and_preserves_other_keys(tmp_path):
    env = tmp_path / "data" / "state" / "testnet" / "credentials.env"
    env.parent.mkdir(parents=True)
    env.write_text("FBOT_MODE=paper\nBAŞKA=deger\n")
    write_keys(tmp_path, "testnet", {"key": "K" * 64, "secret": "S" * 64, "armed": "2026-09-10"})
    txt = env.read_text()
    assert "FBOT_MODE=paper" in txt and "BAŞKA=deger" in txt
    assert f"BINANCE_TESTNET_API_KEY={'K' * 64}" in txt and f"BINANCE_TESTNET_API_SECRET={'S' * 64}" in txt
    assert "FBOT_TESTNET_ARMED=2026-09-10" in txt
    assert stat.S_IMODE(os.stat(env).st_mode) == 0o600


def test_write_updates_existing_values(tmp_path):
    write_keys(tmp_path, "testnet", {"key": "K" * 64, "secret": "S" * 64, "armed": "1"})
    write_keys(tmp_path, "testnet", {"key": "N" * 64, "secret": "M" * 64, "armed": "1"})
    txt = (tmp_path / "data" / "state" / "testnet" / "credentials.env").read_text()
    assert txt.count("BINANCE_TESTNET_API_KEY=") == 1 and "N" * 64 in txt and "K" * 64 not in txt


def test_disarm_clears_flag_but_keeps_key(tmp_path):
    write_keys(tmp_path, "testnet", {"key": "K" * 64, "secret": "S" * 64, "armed": "1"})
    write_keys(tmp_path, "testnet", {"armed": ""})
    txt = (tmp_path / "data" / "state" / "testnet" / "credentials.env").read_text()
    assert "FBOT_TESTNET_ARMED=\n" in txt and f"BINANCE_TESTNET_API_KEY={'K' * 64}" in txt
    assert key_status(tmp_path)["testnet"]["armed"] is False


def test_live_env_uses_different_variable_names(tmp_path):
    write_keys(tmp_path, "live", {"key": "L" * 64, "secret": "X" * 64})
    txt = (tmp_path / ".env").read_text()
    assert f"BINANCE_API_KEY={'L' * 64}" in txt and f"BINANCE_API_SECRET={'X' * 64}" in txt
    assert "BINANCE_TESTNET_API_KEY" not in txt


def test_unknown_env_and_bad_values_rejected(tmp_path):
    with pytest.raises(KeyError_):
        write_keys(tmp_path, "mainnet-prod", {"key": "K" * 64})
    with pytest.raises(KeyError_, match="satır sonu"):
        write_keys(tmp_path, "testnet", {"key": "K" * 30 + "\nBINANCE_API_KEY=hack"})
    with pytest.raises(KeyError_, match="çok kısa"):
        write_keys(tmp_path, "testnet", {"key": "abc"})


def test_live_requires_server_side_gate(tmp_path, monkeypatch):
    """Mainnet anahtarı yalnızca sunucuda açılan kapı ile yazılabilir (web formu tek başına yetmez)."""
    monkeypatch.delenv("FBOT_LIVE_KEYS_ALLOWED", raising=False)
    with pytest.raises(KeyError_, match="FBOT_LIVE_KEYS_ALLOWED"):
        write_keys(tmp_path, "live", {"armed": "1"}, require_gate=True)
    monkeypatch.setenv("FBOT_LIVE_KEYS_ALLOWED", "1")
    write_keys(tmp_path, "live", {"armed": "1"}, require_gate=True)


def test_testnet_keys_go_to_their_own_file_not_env(tmp_path):
    """Testnet anahtarı mainnet anahtarıyla aynı dosyada durmaz: testnet container'ı yalnızca kendi dosyasını görür."""
    from fbot.api.keys import env_path_for, key_status, write_keys
    env = tmp_path / ".env"
    env.write_text("BINANCE_API_KEY=" + "m" * 20 + "\n")
    res = write_keys(tmp_path, "testnet", {"key": "t" * 20, "secret": "s" * 20, "armed": "1"})
    target = env_path_for("testnet", tmp_path)
    assert target == tmp_path / "data" / "state" / "testnet" / "credentials.env"
    assert target.exists() and oct(target.stat().st_mode)[-3:] == "600"
    assert "m" * 20 in env.read_text()                 # mainnet dosyası bozulmadı
    assert "t" * 20 not in env.read_text()             # testnet anahtarı oraya yazılmadı
    st = key_status(tmp_path)
    assert st["testnet"]["key_set"] and st["testnet"]["armed"] and st["testnet"]["masked"] == "…tttt"
    assert res["restart_required"] is False and "10" in res["note"]


def test_live_keys_still_require_the_gate_and_use_dotenv(tmp_path, monkeypatch):
    from fbot.api.keys import KeyError_, env_path_for, write_keys
    monkeypatch.delenv("FBOT_LIVE_KEYS_ALLOWED", raising=False)
    with pytest.raises(KeyError_):
        write_keys(tmp_path, "live", {"key": "l" * 20}, require_gate=True)
    monkeypatch.setenv("FBOT_LIVE_KEYS_ALLOWED", "1")
    res = write_keys(tmp_path, "live", {"key": "l" * 20}, require_gate=True)
    assert env_path_for("live", tmp_path) == tmp_path / ".env"
    assert res["restart_required"] is True


def test_key_file_is_owned_by_the_service_user_when_uid_configured(tmp_path, monkeypatch):
    """Container kök olmayan kullanıcıyla koşar; dosya 600 ise sahibi o kullanıcı olmalı,
    yoksa servis anahtarı hiç okuyamaz (sessiz başarısızlık)."""
    from fbot.api.keys import write_keys
    monkeypatch.setenv("FBOT_SERVICE_UID", str(os.getuid()))
    res = write_keys(tmp_path, "testnet", {"key": "t" * 20, "secret": "s" * 20, "armed": "1"})
    f = tmp_path / "data" / "state" / "testnet" / "credentials.env"
    assert os.stat(f).st_uid == os.getuid() and stat.S_IMODE(os.stat(f).st_mode) == 0o600
    assert res.get("owner_uid") == os.getuid()


def test_bad_service_uid_is_reported_not_fatal(tmp_path, monkeypatch):
    """Sahiplik verilemezse anahtar yine yazılır ama uyarı döner: sessiz başarısızlık olmaz."""
    from fbot.api.keys import write_keys
    monkeypatch.setenv("FBOT_SERVICE_UID", "boyle-bir-kullanici-yok")
    res = write_keys(tmp_path, "testnet", {"key": "t" * 20, "secret": "s" * 20})
    assert (tmp_path / "data" / "state" / "testnet" / "credentials.env").exists()
    assert res["owner_uid"] is None and "uyarı" in res["warning"]
