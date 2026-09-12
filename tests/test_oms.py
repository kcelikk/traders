"""Emir kaydı (Gate 3c): cid → pozisyon/rol çözümü, niyet defteri, durum geçişleri.

Kayıt çekirdekte durur; user data çerçevesi `pos_id` taşımaz. Eşleme I/O kenarında yapılsaydı
replay'de yeniden kurulamaz ve determinizm kırılırdı.
"""
import pytest

from fbot.core.ids import algo_cid, entry_cid, exit_cid
from fbot.core.oms import ACKED, DONE, ENTRY, EXIT, FILLED, PART, PENDING, PROTECTIVE, UNKNOWN, OrderRegistry

POS = entry_cid("t0", "BTCUSDT", 1789200000000, "long")
SL = algo_cid(POS, "SL", 1)
X = exit_cid(POS, "X", 1)


def reg():
    r = OrderRegistry()
    r.register(POS, POS, ENTRY, "BTCUSDT", now_ns=1)
    r.register(SL, POS, PROTECTIVE, "BTCUSDT", now_ns=2)
    return r


def test_position_id_resolves_from_the_registry():
    r = reg()
    assert r.resolve_pos(POS) == POS and r.role_of(POS) == ENTRY
    assert r.resolve_pos(SL) == POS and r.role_of(SL) == PROTECTIVE


def test_unregistered_id_falls_back_to_the_grammar_then_gives_up():
    r = OrderRegistry()
    assert r.resolve_pos(algo_cid(POS, "TP", 2)) == POS      # gramerden çözülür
    assert r.resolve_pos("ios_foreign_order") is None        # yabancı emir: bilinmiyor
    assert r.role_of("ios_foreign_order") is None


def test_unknown_role_is_rejected_at_registration():
    with pytest.raises(ValueError):
        OrderRegistry().register("c1", "p1", "sihir", "X", now_ns=1)


def test_same_cid_is_not_registered_twice():
    r = reg()
    first = r.get(POS)
    assert r.register(POS, "baska", ENTRY, "X", now_ns=9) is first
    assert first.pos_id == POS


def test_intent_ledger_blocks_a_second_order_for_the_same_intent():
    """Gate 0 §5: borsa aynı clientOrderId ile ikinci emri reddetmiyor, ikisi de doluyor.
    Dedupe bu yüzden borsaya değil bu deftere dayanır."""
    r = OrderRegistry()
    r.register(X, POS, EXIT, "BTCUSDT", now_ns=1, intent_key=f"{POS}:close")
    assert r.intent_open(f"{POS}:close")
    r.on_event({"client_id": X, "kind": "order_done", "status": "CANCELED"})
    assert not r.intent_open(f"{POS}:close"), "terminal emir niyeti serbest bırakmalı"
    assert not r.intent_open("hic-kaydedilmemis")


def test_state_moves_forward_only():
    r = reg()
    r.on_event({"client_id": POS, "kind": "order_ack", "status": "NEW", "order_id": 77})
    assert r.get(POS).state == ACKED and r.get(POS).order_id == 77
    r.on_event({"client_id": POS, "kind": "order_fill", "status": "FILLED"})
    assert r.get(POS).state == FILLED
    r.on_event({"client_id": POS, "kind": "order_ack", "status": "NEW"})       # sıra dışı eski olay
    assert r.get(POS).state == FILLED, "terminal durum geriye düşmemeli"


def test_partial_fill_is_not_terminal():
    r = reg()
    r.on_event({"client_id": POS, "kind": "order_fill", "status": "PARTIALLY_FILLED"})
    assert r.get(POS).state == PART and not r.get(POS).is_terminal


def test_algo_events_are_resolved_by_algo_id():
    r = reg()
    r.on_event({"client_algo_id": SL, "kind": "algo_ack"})
    assert r.get(SL).state == ACKED
    r.on_event({"client_algo_id": SL, "kind": "algo_canceled"})
    assert r.get(SL).state == DONE and r.get(SL).is_terminal


def test_foreign_order_events_are_ignored():
    r = reg()
    assert r.on_event({"client_id": "ios_foreign", "kind": "order_fill", "status": "FILLED"}) is None
    assert "ios_foreign" not in r.refs


def test_unknown_marks_and_clears_on_a_terminal_event():
    r = reg()
    r.mark_unknown(POS)
    assert r.get(POS).state == UNKNOWN and POS in r.unknown
    r.on_event({"client_id": POS, "kind": "order_fill", "status": "FILLED"})
    assert r.get(POS).state == FILLED and POS not in r.unknown


def test_terminal_order_cannot_be_marked_unknown():
    r = reg()
    r.on_event({"client_id": POS, "kind": "order_done", "status": "CANCELED"})
    r.mark_unknown(POS)
    assert r.get(POS).state == DONE


def test_sweep_turns_silent_orders_into_unknown():
    """Cevapsız emir sessizce PENDING kalırsa mutabakatın çözmesi gereken durum görünmez olur."""
    r = reg()
    r.on_event({"client_id": SL, "kind": "algo_ack"})           # SL cevap verdi
    moved = r.sweep(now_ns=10_000_000_000, ttl_ns=5_000_000_000)
    assert moved == [POS] and r.get(POS).state == UNKNOWN
    assert r.get(SL).state == ACKED
    assert r.sweep(now_ns=10_000_000_001, ttl_ns=5_000_000_000) == [], "ikinci süpürme tekrar işaretlemez"


def test_open_orders_of_a_position_are_listed_deterministically():
    r = reg()
    r.register(X, POS, EXIT, "BTCUSDT", now_ns=3)
    assert [o.client_id for o in r.open_by_pos(POS)] == sorted([POS, SL, X])
    assert [o.client_id for o in r.open_by_pos(POS, role=PROTECTIVE)] == [SL]
    r.on_event({"client_id": X, "kind": "order_done", "status": "CANCELED"})
    assert X not in [o.client_id for o in r.open_by_pos(POS)]
