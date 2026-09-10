from decimal import Decimal

from fbot.core.commands import BarClosed, StalenessChanged, canonical


def test_canonical_is_deterministic_and_field_ordered():
    b = BarClosed(symbol="BTCUSDT", start_ms=60000, end_ms=119999, open=Decimal("1.0"), high=Decimal("2"),
                  low=Decimal("0.5"), close=Decimal("1.5"), volume=Decimal("3.000"), trades=4)
    c1, c2 = canonical(b), canonical(b)
    assert c1 == c2 and isinstance(c1, bytes)
    assert c1.startswith(b"BarClosed|BTCUSDT|60000|119999|1.0|2|0.5|1.5|3.000|4")


def test_canonical_distinguishes_values():
    a = StalenessChanged(category="public", stale=True, age_ms=31000)
    b = StalenessChanged(category="public", stale=False, age_ms=31000)
    assert canonical(a) != canonical(b)
