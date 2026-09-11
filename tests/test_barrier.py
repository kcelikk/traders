"""SL/TP bariyer değerlendirmesi: bir pozisyonun hangi bariyere, ne zaman çarptığı.

1 dk barında iki bariyer de dokunulmuşsa hangisinin önce olduğu bilinemez; **stop önce** varsayılır
(kötümser). Bu varsayım sonuçları iyimser değil karamsar yönde yanlı yapar, bu yüzden güvenlidir.
"""
from fbot.research.barrier import BarrierConfig, evaluate


def bars(*rows):
    return [{"high": h, "low": lo, "close": c, "open": o} for o, h, lo, c in rows]


CFG = BarrierConfig(sl_pct=1.0, tp_pct=2.0, max_hold=5, cost_pct=0.1)


def test_take_profit_hit_gives_gross_equal_to_tp():
    b = bars((100, 101, 99.5, 100), (100, 102.5, 99.5, 102))
    r = evaluate(entry=100.0, side="long", future=b, cfg=CFG)
    assert r["reason"] == "tp" and round(r["gross_pct"], 6) == 2.0 and r["bars"] == 2
    assert round(r["net_pct"], 6) == 1.9


def test_stop_loss_hit_gives_negative_gross():
    b = bars((100, 100.5, 98.5, 99))
    r = evaluate(entry=100.0, side="long", future=b, cfg=CFG)
    assert r["reason"] == "sl" and round(r["gross_pct"], 6) == -1.0 and round(r["net_pct"], 6) == -1.1


def test_both_barriers_in_one_bar_counts_as_stop():
    b = bars((100, 103, 98, 101))
    assert evaluate(entry=100.0, side="long", future=b, cfg=CFG)["reason"] == "sl"


def test_timeout_exits_at_close_of_last_bar():
    b = bars(*[(100, 100.5, 99.5, 100.2)] * 5)
    r = evaluate(entry=100.0, side="long", future=b, cfg=CFG)
    assert r["reason"] == "timeout" and round(r["gross_pct"], 4) == 0.2 and r["bars"] == 5


def test_short_side_mirrors_the_barriers():
    up = bars((100, 101.2, 99, 101))
    assert evaluate(entry=100.0, side="short", future=up, cfg=CFG)["reason"] == "sl"
    down = bars((100, 100.5, 97.9, 98))
    r = evaluate(entry=100.0, side="short", future=down, cfg=CFG)
    assert r["reason"] == "tp" and round(r["gross_pct"], 6) == 2.0


def test_not_enough_future_bars_returns_none():
    assert evaluate(entry=100.0, side="long", future=[], cfg=CFG) is None


def test_cost_is_always_subtracted():
    b = bars((100, 102.5, 99.6, 102))
    r = evaluate(entry=100.0, side="long", future=b, cfg=BarrierConfig(1.0, 2.0, 5, cost_pct=0.25))
    assert round(r["net_pct"], 6) == 1.75


def test_scan_reports_a_pass_only_when_both_halves_clear_zero(monkeypatch):
    """Keşif geçip doğrulama geçmezse "geçti" yazılmaz: eşiği gevşetmek sonuç aramaktır."""
    from scripts.barrier_scan import scan
    # hiçbir bariyere dokunmayan düz fiyat: her giriş süre dolunca kapanışta çıkar, net sıfır
    rows = [{"symbol": "X", "start_ms": i * 60000, "open": 100, "high": 100.1, "low": 99.9,
             "close": 100.0, "spread_bps": 0.0} for i in range(400)]
    labels = {"X": ["S1"] * 400}
    out = scan({"X": rows}, labels, fee_in=0.0, fee_out=0.0, disc_frac=0.7,
               n_boot=50, seed=1, alpha=0.05, min_n=10)
    assert out, "birleşim üretilmedi"
    assert all(r["gecti"] is False for r in out)          # net sıfır: CI'nin alt sınırı sıfırın üstünde değil
    assert all(abs(r["val_mean"]) < 1e-9 for r in out)
    assert {r["state"] for r in out} == {"S1"}


def test_stride_reduces_sample_without_changing_the_shape():
    from scripts.barrier_scan import scan
    rows = [{"symbol": "X", "start_ms": i * 60000, "open": 100, "high": 101, "low": 99,
             "close": 100.0, "spread_bps": 0.0} for i in range(600)]
    labels = {"X": ["S2"] * 600}
    a = scan({"X": rows}, labels, 0.0, 0.0, 0.7, 20, 1, 0.05, 10, stride=1)[0]
    b = scan({"X": rows}, labels, 0.0, 0.0, 0.7, 20, 1, 0.05, 10, stride=3)[0]
    assert b["n_val"] < a["n_val"] and b["state"] == a["state"]


def test_finalists_are_remeasured_with_the_full_bootstrap():
    """Eleme ucuz bootstrap'la yapılır; kararı veren ölçüm tam sayıyla tekrarlanır."""
    import random
    from scripts.barrier_scan import scan
    rng = random.Random(5)
    rows, px = [], 100.0
    for i in range(900):
        px *= 1 + rng.gauss(0, 0.001)
        rows.append({"symbol": "X", "start_ms": i * 60000, "open": px, "high": px * 1.002,
                     "low": px * 0.998, "close": px, "spread_bps": 0.0})
    out = scan({"X": rows}, {"X": ["S1"] * 900}, 0.0, 0.0, 0.7, n_boot=400, seed=1,
               alpha=0.05, min_n=10, screen_boot=50)
    assert out[0]["boot"] == 400                      # en iyi birleşim tam ölçüldü
    assert all("_val" not in r for r in out)          # ham örnekler raporda taşınmaz


def fbars(*rows):
    """(o,h,l,c,funding_rate,next_funding_ms) — funding sınırı geçildiğinde ödeme yapılır."""
    return [{"open": o, "high": h, "low": lo, "close": c, "funding_rate": fr, "next_funding_ms": nf}
            for o, h, lo, c, fr, nf in rows]


FCFG = BarrierConfig(sl_pct=5.0, tp_pct=5.0, max_hold=4, cost_pct=0.0, funding=True)


def test_funding_is_charged_when_a_settlement_is_crossed():
    """Uzun tutmada funding maliyeti yok sayılamaz: 8 saatte bir ödenir."""
    b = fbars((100, 100.5, 99.5, 100, 0.0001, 1000), (100, 100.5, 99.5, 100, 0.0001, 1000),
              (100, 100.5, 99.5, 100, 0.0001, 9000), (100, 100.5, 99.5, 101, 0.0001, 9000))
    r = evaluate(entry=100.0, side="long", future=b, cfg=FCFG)
    assert r["reason"] == "timeout"
    assert round(r["funding_pct"], 6) == 0.01          # tek ödeme, %0,01
    assert round(r["net_pct"], 6) == round(1.0 - 0.01, 6)


def test_short_receives_funding_when_the_rate_is_positive():
    b = fbars((100, 100.5, 99.5, 100, 0.0001, 1000), (100, 100.5, 99.5, 100, 0.0001, 9000))
    r = evaluate(entry=100.0, side="short", future=b, cfg=BarrierConfig(5.0, 5.0, 2, 0.0, funding=True))
    assert round(r["funding_pct"], 6) == -0.01
    assert r["net_pct"] > r["gross_pct"]


def test_no_settlement_crossed_means_no_funding():
    b = fbars((100, 100.5, 99.5, 100, 0.0001, 9000), (100, 100.5, 99.5, 100, 0.0001, 9000))
    r = evaluate(entry=100.0, side="long", future=b, cfg=BarrierConfig(5.0, 5.0, 2, 0.0, funding=True))
    assert r["funding_pct"] == 0.0


def test_funding_disabled_keeps_the_old_behaviour():
    b = fbars((100, 100.5, 99.5, 100, 0.01, 1000), (100, 100.5, 99.5, 100, 0.01, 9000))
    r = evaluate(entry=100.0, side="long", future=b, cfg=BarrierConfig(5.0, 5.0, 2, 0.1))
    assert r["funding_pct"] == 0.0 and round(r["net_pct"], 6) == -0.1


def test_funding_only_counts_bars_actually_held():
    """Bariyer 1. barda vurulduysa sonraki barların funding'i yazılmaz."""
    b = fbars((100, 106, 99.5, 105, 0.001, 1000), (100, 100.5, 99.5, 100, 0.001, 9000),
              (100, 100.5, 99.5, 100, 0.001, 20000))
    r = evaluate(entry=100.0, side="long", future=b, cfg=BarrierConfig(5.0, 5.0, 3, 0.0, funding=True))
    assert r["reason"] == "tp" and r["bars"] == 1 and r["funding_pct"] == 0.0
