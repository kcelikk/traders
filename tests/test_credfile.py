"""Anahtar dosyasının çalışırken okunması: konsoldan anahtar değişince servis yeniden başlamamalı."""
import pytest

from fbot.gateway.credfile import CredState, read_env_file, read_testnet_state


def w(p, **kv):
    p.write_text("".join(f"{k}={v}\n" for k, v in kv.items()))
    return p


def test_env_file_is_parsed_with_comments_and_quotes(tmp_path):
    f = tmp_path / ".env"
    f.write_text('# yorum\nA=1\n  B = iki \nC="üç"\nD=\'dört\'\nBOZUK\n\n')
    env = read_env_file(f)
    assert env == {"A": "1", "B": "iki", "C": "üç", "D": "dört"}


def test_missing_file_is_empty_not_error(tmp_path):
    assert read_env_file(tmp_path / "yok") == {}


def test_armed_requires_flag_key_and_secret(tmp_path):
    f = tmp_path / ".env"
    s = read_testnet_state(w(f, BINANCE_TESTNET_API_KEY="k" * 20, BINANCE_TESTNET_API_SECRET="s" * 20))
    assert s.armed is False and "FBOT_TESTNET_ARMED" in s.reason
    s = read_testnet_state(w(f, FBOT_TESTNET_ARMED="1", BINANCE_TESTNET_API_KEY="k" * 20))
    assert s.armed is False and "SECRET" in s.reason
    s = read_testnet_state(w(f, FBOT_TESTNET_ARMED="1", BINANCE_TESTNET_API_KEY="k" * 20, BINANCE_TESTNET_API_SECRET="s" * 20))
    assert s.armed is True and s.creds.api_key == "k" * 20


def test_fingerprint_changes_with_content_and_never_leaks_secret(tmp_path):
    f = tmp_path / ".env"
    a = read_testnet_state(w(f, FBOT_TESTNET_ARMED="1", BINANCE_TESTNET_API_KEY="k" * 20, BINANCE_TESTNET_API_SECRET="s" * 20))
    b = read_testnet_state(w(f, FBOT_TESTNET_ARMED="1", BINANCE_TESTNET_API_KEY="k" * 20, BINANCE_TESTNET_API_SECRET="t" * 20))
    assert a.fingerprint != b.fingerprint and len(a.fingerprint) == 12
    blob = repr(a) + a.reason + a.masked
    assert "s" * 20 not in blob and "k" * 20 not in blob


def test_disarmed_state_carries_no_credentials(tmp_path):
    s = read_testnet_state(tmp_path / "yok")
    assert isinstance(s, CredState) and s.creds is None and s.armed is False


def test_empty_armed_value_is_not_armed(tmp_path):
    f = tmp_path / ".env"
    s = read_testnet_state(w(f, FBOT_TESTNET_ARMED="", BINANCE_TESTNET_API_KEY="k" * 20, BINANCE_TESTNET_API_SECRET="s" * 20))
    assert s.armed is False


def test_process_env_is_fallback_when_file_lacks_value(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    w(f, FBOT_TESTNET_ARMED="1")
    monkeypatch.setenv("BINANCE_TESTNET_API_KEY", "k" * 20)
    monkeypatch.setenv("BINANCE_TESTNET_API_SECRET", "s" * 20)
    assert read_testnet_state(f).armed is True


def test_later_file_overrides_earlier_one(tmp_path):
    from fbot.gateway.credfile import testnet_paths
    a, b = tmp_path / ".env", tmp_path / "data" / "state" / "credentials.env"
    b.parent.mkdir(parents=True)
    w(a, FBOT_TESTNET_ARMED="1", BINANCE_TESTNET_API_KEY="e" * 20, BINANCE_TESTNET_API_SECRET="s" * 20)
    w(b, BINANCE_TESTNET_API_KEY="y" * 20, BINANCE_TESTNET_API_SECRET="z" * 20)
    st = read_testnet_state(testnet_paths(tmp_path), environ={})
    assert st.armed is True and st.creds.api_key == "y" * 20      # yeni dosya kazanır
    assert st.masked == "…yyyy"


def test_paths_list_tolerates_missing_files(tmp_path):
    from fbot.gateway.credfile import testnet_paths
    assert read_testnet_state(testnet_paths(tmp_path), environ={}).armed is False


def test_console_writes_where_the_service_reads(tmp_path):
    """Sözleşme: konsolun yazdığı dosya, servisin okuduğu yollar listesinde olmalı.

    Bu bağ koptuğunda servis anahtarı hiç görmez ve hata sessizdir; testnet silahsız kalır.
    """
    from fbot.api.keys import env_path_for
    from fbot.gateway.credfile import testnet_paths
    assert env_path_for("testnet", tmp_path) in testnet_paths(tmp_path)


def test_service_reads_the_console_file_in_container_layout(tmp_path):
    """Container'da host `data/state/testnet` dizini `/app/data/state` olarak bağlanır."""
    from fbot.gateway.credfile import testnet_paths
    assert tmp_path / "data" / "state" / "credentials.env" in testnet_paths(tmp_path)


def test_unreadable_file_is_reported_not_silently_ignored(tmp_path):
    """İzin hatası sessizce 'değişiklik yok'a dönüşmemeli: servis eski anahtarla silahlı kalırdı."""
    import os
    import pytest as _pytest
    from fbot.gateway.credfile import EnvFileUnreadable, read_env_file
    f = tmp_path / "gizli.env"
    f.write_text("A=1\n")
    os.chmod(f, 0o000)
    if os.geteuid() == 0:
        _pytest.skip("root her dosyayı okur; izin senaryosu kök olmayan kullanıcıda anlamlı")
    with _pytest.raises(EnvFileUnreadable):
        read_env_file(f)


def test_unreadable_file_makes_state_disarmed_with_reason(tmp_path, monkeypatch):
    from fbot.gateway import credfile
    def boom(p):
        raise credfile.EnvFileUnreadable(f"{p}: izin yok")
    monkeypatch.setattr(credfile, "read_env_file", boom)
    st = credfile.read_testnet_state(tmp_path / "x.env",
                                     environ={"FBOT_TESTNET_ARMED": "1", "BINANCE_TESTNET_API_KEY": "k" * 20,
                                              "BINANCE_TESTNET_API_SECRET": "s" * 20})
    assert st.armed is False and "izin yok" in st.reason
    assert st.fingerprint.startswith("err-")
