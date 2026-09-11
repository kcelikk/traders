"""İşlem geçmişi ve performans ekranının veri ucu (madde 5)."""
from fbot.api.history import history
from fbot.paper.store import PaperStore


def mk(tmp_path, n=5):
    d = tmp_path / "paper-h"; d.mkdir()
    s = PaperStore(d / "paper.db", run_id="paper-h", env="paper")
    for i in range(n):
        s.record_position({"pos_id": f"p{i}", "symbol": "BTCUSDT" if i % 2 else "ETHUSDT", "side": "long",
                           "state": "CLOSED", "qty": "0", "entry_price": "100", "sl": None, "tp": None,
                           "net_pct": str(0.5 if i % 2 else -0.3), "exit_reason": "tp" if i % 2 else "sl",
                           "opened_ns": i * 10, "closed_ns": i * 10 + 5, "entry_state": "S1",
                           "exit_price": "101", "filled_qty": "0.8"})
    s.flush(); s.close()
    return d / "paper.db"


def test_history_is_newest_first_and_paged(tmp_path):
    mk(tmp_path, n=5)
    h = history(tmp_path, run_id="paper-h", limit=2, offset=0)
    assert [t["pos_id"] for t in h["trades"]] == ["p4", "p3"]
    assert h["total"] == 5 and h["limit"] == 2 and h["offset"] == 0
    assert history(tmp_path, run_id="paper-h", limit=2, offset=2)["trades"][0]["pos_id"] == "p2"


def test_trade_rows_carry_price_quantity_and_duration(tmp_path):
    mk(tmp_path, n=1)
    t = history(tmp_path, run_id="paper-h")["trades"][0]
    assert t["exit_price"] == "101" and t["notional_usdt"] == 80.0
    assert t["hold_ms"] == 0 and t["net_usdt"] is not None


def test_performance_breaks_down_by_symbol_reason_and_state(tmp_path):
    mk(tmp_path, n=6)
    p = history(tmp_path, run_id="paper-h")["performance"]
    assert p["by_symbol"]["BTCUSDT"]["n"] == 3 and p["by_symbol"]["BTCUSDT"]["net_pct"] == 1.5
    assert p["by_exit_reason"]["sl"]["n"] == 3
    assert p["by_entry_state"]["S1"]["n"] == 6
    assert p["equity"][-1]["cum_net_pct"] == round(3 * 0.5 - 3 * 0.3, 4)


def test_unknown_run_returns_empty_not_another_run(tmp_path):
    mk(tmp_path, n=2)
    h = history(tmp_path, run_id="yok")
    assert h["trades"] == [] and h["run_missing"] is True and h["run_id"] is None


def test_usdt_totals_are_unknown_not_zero_when_quantity_missing(tmp_path):
    """Miktarı bilinmeyen işlemlerde USDT toplamı 0,00 yazmak yanlış bilgi verir."""
    d = tmp_path / "paper-h"; d.mkdir()
    s = PaperStore(d / "paper.db", run_id="paper-h", env="paper")
    s.record_position({"pos_id": "p", "symbol": "X", "side": "long", "state": "CLOSED", "qty": "0", "entry_price": "100",
                       "sl": None, "tp": None, "net_pct": "-0.1", "exit_reason": "sl", "opened_ns": 1, "closed_ns": 2,
                       "entry_state": "S1", "exit_price": "99"})
    s.flush(); s.close()
    p = history(tmp_path, run_id="paper-h")["performance"]
    assert p["by_symbol"]["X"]["net_usdt"] is None
    assert p["by_symbol"]["X"]["net_pct"] == -0.1
