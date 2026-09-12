"""Emir düzeyi golden baseline + Gate 2.0 doğruluk değişmezleri.

`tests/golden/replay_baseline.json` yalnız `rec-mini` fixture'ını kapsıyor; o fixture'da strateji
kapalı olduğu için sadece `BarClosed` üretiliyor. Tetik fiyatı ve `clientOrderId` alanlarındaki bir
regresyonu o baseline yakalamıyordu. Bu dosya o boşluğu kapatır.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.golden_orders import build

GOLDEN = Path("tests/golden/orders_baseline.json")
TICK = Decimal("0.01")        # tests/scenario.py FILT
STEP = Decimal("0.001")
MAX_CID = 36                  # Binance -4015; 36 dahil kabul ediliyor (Gate 0 testnet doğrulaması)


@pytest.fixture(scope="module")
def current() -> dict:
    return build()


@pytest.fixture(scope="module")
def golden() -> dict:
    return json.loads(GOLDEN.read_text())


@pytest.mark.golden
def test_command_stream_matches_the_pinned_baseline(current, golden):
    assert current["hash"] == golden["hash"], (
        "Emir dizisi değişti. Kasıtlıysa: ADR yaz, `python -m scripts.golden_orders --diff "
        "tests/golden/orders_baseline.json` ile alan tablosunu üret, sonra baseline'ı yenile."
    )
    assert current["commands"] == golden["commands"]
    assert current["by_kind"] == golden["by_kind"]


def test_every_trigger_price_sits_on_a_tick(current):
    """Gate 0 testnet doğrulaması: borsa tetik fiyatında tickSize zorlamıyor, ama tetik gerçek bir
    fiyat seviyesine denk gelmeli; aksi hâlde koruma fiyatı ile defter arasında sistematik sapma olur."""
    bad = [r for r in current["rows"] if r["cmd"] == "PlaceAlgo" and Decimal(r["trigger_price"]) % TICK != 0]
    assert not bad, f"tick'e oturmayan {len(bad)} tetik fiyatı, ilki: {bad[0]}"


def test_every_quantity_sits_on_a_step(current):
    bad = [r for r in current["rows"] if r["cmd"] == "PlaceOrder" and Decimal(r["qty"]) % STEP != 0]
    assert not bad, f"step'e oturmayan {len(bad)} miktar, ilki: {bad[0]}"


def test_no_client_id_can_exceed_the_exchange_limit(current):
    """`pos_id` zaten 36'ya kırpılmışken `-SL-v1` eklenince 42 karaktere çıkıyordu → -4015."""
    ids = [r.get("client_id") or r.get("client_algo_id") for r in current["rows"] if r["cmd"] != "StateChanged"]
    over = [i for i in ids if i and len(i) > MAX_CID]
    assert not over, f"36 karakteri aşan kimlik: {over[:3]}"


def test_position_id_is_recoverable_from_every_order_id(current):
    """Simülatör ve trader, exec olayında `pos_id`'yi kimliğin önekinden çözüyor; gramer bunu korumalı."""
    from fbot.core.ids import pos_id_of
    entry = [r["client_id"] for r in current["rows"] if r["cmd"] == "PlaceOrder" and not r["reduce_only"]]
    assert entry
    for r in current["rows"]:
        cid = r.get("client_algo_id") or r.get("client_id")
        if r["cmd"] in ("PlaceAlgo", "CancelAlgo") or (r["cmd"] == "PlaceOrder" and r["reduce_only"]):
            assert pos_id_of(cid) in entry, f"{cid} hiçbir girişe bağlanmıyor"
