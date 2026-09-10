import json

from fbot.integrity import SeqChecker, StreamChecker


def frame(stream, **data):
    return json.dumps({"stream": stream, "data": data}).encode()


def test_seq_checker_counts_gaps_and_dups():
    c = SeqChecker()
    for s in (1, 2, 3, 5, 5, 6):
        c.feed(s)
    r = c.report()
    assert r["gaps"] == 1 and r["missing"] == 1 and r["dups"] == 1
    assert r["first"] == 1 and r["last"] == 6 and r["count"] == 6


def test_aggtrade_id_continuity():
    c = StreamChecker()
    for a in (10, 11, 12, 14):
        c.feed("btcusdt@aggTrade", frame("btcusdt@aggTrade", e="aggTrade", a=a, E=1))
    r = c.report()["btcusdt@aggTrade"]
    assert r["count"] == 4 and r["breaks"] == 1


def test_bookticker_update_id_must_not_decrease():
    c = StreamChecker()
    for u in (5, 6, 6, 4):
        c.feed("btcusdt@bookTicker", frame("btcusdt@bookTicker", e="bookTicker", u=u, E=1))
    assert c.report()["btcusdt@bookTicker"]["breaks"] == 1


def test_depth_pu_chain():
    c = StreamChecker()
    c.feed("btcusdt@depth@100ms", frame("btcusdt@depth@100ms", e="depthUpdate", U=1, u=3, pu=0, E=1))
    c.feed("btcusdt@depth@100ms", frame("btcusdt@depth@100ms", e="depthUpdate", U=4, u=6, pu=3, E=1))
    c.feed("btcusdt@depth@100ms", frame("btcusdt@depth@100ms", e="depthUpdate", U=9, u=9, pu=8, E=1))  # kopuş
    r = c.report()["btcusdt@depth@100ms"]
    assert r["breaks"] == 1 and r["count"] == 3


def test_reset_on_reconnect_does_not_count_as_break():
    c = StreamChecker()
    c.feed("btcusdt@depth@100ms", frame("btcusdt@depth@100ms", e="depthUpdate", U=1, u=3, pu=0, E=1))
    c.reset("public")  # kategori yeniden bağlandı
    c.feed("btcusdt@depth@100ms", frame("btcusdt@depth@100ms", e="depthUpdate", U=50, u=52, pu=49, E=1))
    assert c.report()["btcusdt@depth@100ms"]["breaks"] == 0


def test_event_time_monotonic_violations_are_counted_not_raised():
    c = StreamChecker()
    c.feed("x@aggTrade", frame("x@aggTrade", e="aggTrade", a=1, E=100))
    c.feed("x@aggTrade", frame("x@aggTrade", e="aggTrade", a=2, E=90))
    assert c.report()["x@aggTrade"]["E_regressions"] == 1
