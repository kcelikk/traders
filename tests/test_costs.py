from decimal import Decimal

from fbot.costs import CostConfig, commission, funding_payment, slippage_cost

CFG = CostConfig(maker_rate=Decimal("0.0002"), taker_rate=Decimal("0.0005"), bnb_discount=Decimal("0.10"), funding_interval_h=8)


def test_commission_maker_taker_and_bnb():
    assert commission(Decimal("100"), is_maker=False, cfg=CFG, pay_with_bnb=False) == Decimal("0.0500")
    assert commission(Decimal("100"), is_maker=True, cfg=CFG, pay_with_bnb=False) == Decimal("0.0200")
    assert commission(Decimal("100"), is_maker=False, cfg=CFG, pay_with_bnb=True) == Decimal("0.045000")


def test_funding_sign_long_pays_positive_rate():
    # long, pozitif oran → öder (negatif nakit akışı)
    assert funding_payment(Decimal("1000"), Decimal("0.0001"), side="long") == Decimal("-0.1000")
    assert funding_payment(Decimal("1000"), Decimal("0.0001"), side="short") == Decimal("0.1000")
    assert funding_payment(Decimal("1000"), Decimal("-0.0002"), side="long") == Decimal("0.2000")


def test_slippage_cost_from_book_walk():
    asks = [(Decimal("100"), Decimal("1")), (Decimal("101"), Decimal("1"))]
    # 150 USDT alış: 1.0 @100 + 0.495.. @101 → ort > 100; maliyet = (ort − best) × miktar
    c = slippage_cost(asks, notional=Decimal("150"), best=Decimal("100"), side="buy")
    # miktar = 1 + 50/101; maliyet = (ort − best) × miktar = 150 − 100 × miktar = 50 − 5000/101
    expected = Decimal(50) - Decimal(5000) / Decimal(101)
    assert c > 0 and abs(c - expected) < Decimal("1e-20")


def test_slippage_insufficient_depth_is_none():
    assert slippage_cost([(Decimal("100"), Decimal("1"))], notional=Decimal("1000"), best=Decimal("100"), side="buy") is None
