from fbot.sequencer import Sequencer


def test_sequence_is_monotonic_and_gapless():
    sq = Sequencer()
    evs = [sq.next(recv_ns=10 + i, mono_ns=i, cat="public", stream="x", raw=b"{}") for i in range(5)]
    assert [e.seq for e in evs] == [1, 2, 3, 4, 5]
    assert sq.last_seq == 5


def test_sequence_can_resume_from_manifest():
    sq = Sequencer(start=100)
    assert sq.next(1, 1, "ctrl", "run_start", b"{}").seq == 101


def test_sequencer_ignores_time_ordering():
    # sıralama alım sırasıdır, zaman damgası değil (Rule Zero: tek sıralama noktası)
    sq = Sequencer()
    a = sq.next(recv_ns=200, mono_ns=2, cat="public", stream="x", raw=b"{}")
    b = sq.next(recv_ns=100, mono_ns=1, cat="market", stream="y", raw=b"{}")
    assert a.seq < b.seq
