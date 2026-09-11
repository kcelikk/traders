from pathlib import Path

from fbot.paper.store import PaperStore
from scripts.paper_summary import metrics


def pos(i, net, reason, o=1, c=2):
    return {"pos_id": f"p{i}", "symbol": "X", "side": "long", "state": "CLOSED", "qty": "0", "entry_price": "100",
            "sl": None, "tp": None, "net_pct": str(net), "exit_reason": reason, "opened_ns": o, "closed_ns": c, "entry_state": "S1"}


def test_metrics_cover_bolum12_set(tmp_path):
    db = tmp_path / "p.db"
    s = PaperStore(db, run_id="r")
    for i, (net, reason) in enumerate([(1.0, "tp"), (-0.5, "sl"), (0.8, "tp"), (-0.6, "sl"), (-0.4, "timeout")]):
        s.record_position(pos(i, net, reason, o=i * 60_000_000_000, c=(i + 2) * 60_000_000_000))
    s.record_decision({"t_ms": 1, "symbol": "X", "kind": "REJECT", "reasons": ["K3_warmup", "K13_spread"], "cell": "c", "explain": ""})
    s.record_decision({"t_ms": 2, "symbol": "X", "kind": "APPROVE", "reasons": [], "cell": "c", "explain": ""})
    s.flush()
    m = metrics(db)
    assert m["işlem"] == 5 and m["kazanma_oranı"] == 0.4
    assert m["net_toplam_pct"] == 0.3 and m["beklenti_pct"] == 0.06
    assert m["profit_factor"] == round(1.8 / 1.5, 3)
    assert m["maks_drawdown_pct"] > 0 and m["risk_ayarlı"] is not None
    assert m["çıkış_nedenleri"] == {"tp": 2, "sl": 2, "timeout": 1}
    assert m["ret_nedenleri"] == {"K3_warmup": 1, "K13_spread": 1}
    assert m["ortalama_tutma_dk"] == 2.0
    assert "ADR 0010" in m["not"] and "ADR 0013" in m["not"]


def test_empty_db_does_not_crash(tmp_path):
    s = PaperStore(tmp_path / "e.db", run_id="r"); s.flush()
    m = metrics(tmp_path / "e.db")
    assert m["işlem"] == 0 and m["net_ortalama_pct"] is None


def test_drawdown_follows_time_order_not_insertion_order(tmp_path):
    """Sıralamasız sorgu drawdown'ı rastgele bir diziden hesaplıyordu (F08)."""
    db = tmp_path / "dd.db"
    s = PaperStore(db, run_id="r")
    # kapanış sırası: +1.0, -2.0, +0.5 → maks drawdown 2.0
    rows = [("a", "0.5", 3), ("b", "1.0", 1), ("c", "-2.0", 2)]
    for pid, net, k in rows:
        s.record_position({"pos_id": pid, "symbol": "X", "side": "long", "state": "CLOSED", "qty": "0", "entry_price": "100",
                           "sl": None, "tp": None, "net_pct": net, "exit_reason": "tp", "opened_ns": k, "closed_ns": k * 10,
                           "entry_state": "S1", "exit_price": "101"})
    s.flush(); s.close()
    m = metrics(db)
    assert m["maks_drawdown_pct"] == 2.0
    assert m["net_toplam_pct"] == -0.5
