from fbot.clock import ReplayClock


def test_replay_clock_is_set_explicitly_and_monotone_guard():
    c = ReplayClock()
    c.set(100)
    assert c.now_ns() == 100
    c.set(50)              # geriye giden event zamanı saati geri almaz
    assert c.now_ns() == 100
    c.set(200)
    assert c.now_ns() == 200
