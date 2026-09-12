"""Koşu kimliği: her satırın hangi koşuya, moda, stratejiye ve kod sürümüne ait olduğu.

Bu alanlar olmadan strateji başına PnL atfı imkânsızdır ve sonradan eklenmesi şema göçü gerektirir.
Bu yüzden async persistence ile **aynı anda** eklenir; şemaya iki kez dokunulmaz.
"""
import json
from pathlib import Path

import pytest

from fbot.identity import ROW_COLS, RunIdentity, code_hash, semantic_hash


def test_identity_carries_every_attribution_field():
    i = RunIdentity(run_id="r1", mode="paper", strategy_id="v1", strategy_version="0.1",
                    config_hash="abc", config_semantic_hash="def", code_hash="c0", git_sha="g0", restart_no=2)
    d = i.as_dict()
    assert set(d) == {"run_id", "mode", "strategy_id", "strategy_version", "config_hash",
                      "config_semantic_hash", "code_hash", "reactor_id", "git_sha", "restart_no"}
    assert d["mode"] == "paper" and d["restart_no"] == 2


def test_row_matches_row_cols_order():
    """Satır kimliği ile sütun adları tek yerde tanımlı: eşleşme kayarsa yanlış sütuna yazılır."""
    i = RunIdentity(run_id="r1", mode="testnet", strategy_id="s", strategy_version="2",
                    config_hash="a", config_semantic_hash="b", code_hash="c", git_sha="g", restart_no=0,
                    reactor_id="rx")
    assert len(i.row()) == len(ROW_COLS)
    assert dict(zip(ROW_COLS, i.row())) == {"mode": "testnet", "strategy_id": "s", "strategy_version": "2",
                                            "code_hash": "c", "reactor_id": "rx"}


def test_reactor_id_defaults_to_none_until_gate4():
    i = RunIdentity(run_id="r", mode="replay", strategy_id=None, strategy_version=None, config_hash="a",
                    config_semantic_hash="b", code_hash="c", git_sha="g", restart_no=0)
    assert i.reactor_id is None


def test_mode_must_be_known():
    with pytest.raises(ValueError, match="bilinmeyen mod"):
        RunIdentity(run_id="r", mode="canli", strategy_id=None, strategy_version=None,
                    config_hash="a", config_semantic_hash="b", code_hash="c", git_sha="g", restart_no=0)


def test_code_hash_changes_with_content_and_is_stable_otherwise(tmp_path):
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "a.py").write_text("x = 1\n")
    (pkg / "b.py").write_text("y = 2\n")
    h1 = code_hash(pkg)
    assert h1 == code_hash(pkg)                  # aynı içerik → aynı hash
    (pkg / "b.py").write_text("y = 3\n")
    assert code_hash(pkg) != h1                  # içerik değişti → hash değişti
    assert len(h1) == 12


def test_code_hash_ignores_caches_and_non_python(tmp_path):
    pkg = tmp_path / "pkg"
    (pkg / "__pycache__").mkdir(parents=True)
    (pkg / "a.py").write_text("x = 1\n")
    h1 = code_hash(pkg)
    (pkg / "__pycache__" / "a.pyc").write_bytes(b"derlenmis")
    (pkg / "notlar.md").write_text("aciklama")
    assert code_hash(pkg) == h1


def test_semantic_hash_ignores_comments_but_not_values():
    """Ham bayt hash'i yorum değişince de değişir; anlamsal hash yalnız etkin değere bakar."""
    a = semantic_hash({"risk": {"max_positions": 5}, "sim": {"seed": 1}})
    b = semantic_hash({"sim": {"seed": 1}, "risk": {"max_positions": 5}})   # anahtar sırası farklı
    c = semantic_hash({"risk": {"max_positions": 4}, "sim": {"seed": 1}})
    assert a == b and a != c and len(a) == 12


def test_missing_code_dir_is_an_error_not_a_silent_default(tmp_path):
    with pytest.raises(FileNotFoundError):
        code_hash(tmp_path / "yok")
