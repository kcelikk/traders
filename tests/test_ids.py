"""`clientOrderId` grameri (Gate 2.0): uzunluk sınırı girdiden bağımsız olmalı."""
import pytest

from fbot.core.ids import MAX_LEN, algo_cid, check, entry_cid, exit_cid, pos_id_of


def test_entry_id_length_does_not_depend_on_symbol_or_time():
    a = entry_cid("f1", "BTCUSDT", 1789200000000, "long")
    b = entry_cid("f1", "1000000BABYDOGEUSDT", 1789200000000, "short")
    assert len(a) == len(b) <= 15


def test_protection_ids_stay_under_the_exchange_limit():
    """Eski gramerde kırpılmış 36 karakterlik pos_id'ye '-SL-v1' eklenince 42 oluyordu (-4015)."""
    pos = entry_cid("f1", "1000000BABYDOGEUSDT", 1789200000000, "short")
    for role in ("SL", "TP"):
        for v in (1, 99):
            assert len(algo_cid(pos, role, v)) <= MAX_LEN
    assert len(exit_cid(pos, "X", 7)) <= MAX_LEN


def test_same_inputs_give_the_same_id():
    assert entry_cid("f1", "XUSDT", 5, "long") == entry_cid("f1", "XUSDT", 5, "long")


def test_different_direction_or_bar_gives_a_different_id():
    base = entry_cid("f1", "XUSDT", 5, "long")
    assert base != entry_cid("f1", "XUSDT", 5, "short")
    assert base != entry_cid("f1", "XUSDT", 6, "long")
    assert base != entry_cid("f2", "XUSDT", 5, "long")


def test_position_id_is_recoverable():
    pos = entry_cid("f1", "XUSDT", 5, "long")
    assert pos_id_of(algo_cid(pos, "SL", 3)) == pos
    assert pos_id_of(exit_cid(pos, "X", 1)) == pos
    assert pos_id_of(pos) == pos


def test_over_long_id_raises_at_the_point_of_creation():
    with pytest.raises(ValueError, match="36"):
        check("x" * 37)


def test_tag_must_be_short_and_separator_free():
    for bad in ("", "toolongtag", "f-1"):
        with pytest.raises(ValueError):
            entry_cid(bad, "XUSDT", 1, "long")
