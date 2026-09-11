"""Kill switch ortama bağlıdır: paper'ı durdurmak istenirken canlının dosyası yazılmamalı (F01)."""
import pytest

from fbot.api.envmap import UnknownEnv, kill_path_for, known_envs


def test_each_env_maps_to_its_own_file(tmp_path):
    paths = {e: kill_path_for(e, tmp_path) for e in known_envs()}
    assert len(set(paths.values())) == len(paths)
    assert paths["paper"] == tmp_path / "data" / "state" / "kill_switch.json"
    assert paths["testnet"] == tmp_path / "data" / "state" / "testnet" / "kill_switch.json"
    assert paths["live"] == tmp_path / "data" / "state" / "live" / "kill_switch.json"


def test_unknown_env_is_rejected_not_defaulted(tmp_path):
    with pytest.raises(UnknownEnv):
        kill_path_for("../../etc", tmp_path)
    with pytest.raises(UnknownEnv):
        kill_path_for(None, tmp_path)
