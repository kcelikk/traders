"""Kullanılmayan veriden üretilen giriş sinyalleri (H6–H8).

Hepsi yalnızca geçmişe bakar: bir barın sinyali, o bar ve öncesindeki değerlerden çıkar.
Yetersiz geçmişte sinyal yoktur (None), tahmin edilmez.
"""
from fbot.research.signals import SIGNALS, signal_series

M = 60_000


def bars(vals, key, n=None):
    """`key` alanına verilen değerleri taşıyan bar dizisi."""
    out = []
    for i, v in enumerate(vals):
        b = {"symbol": "X", "start_ms": i * M, "end_ms": (i + 1) * M, "open": 100, "high": 101,
             "low": 99, "close": 100, "volume": 1.0, "buy_volume": 0.5, "trades": 3, "spread_bps": 1.0,
             "book_imb": None, "depth_usdt": None, "open_interest": None, "taker_ls_ratio": None,
             "account_ls_ratio": None, "toptrader_ls_ratio": None}
        b[key] = v
        out.append(b)
    return out


def test_every_registered_signal_returns_one_label_per_bar():
    rows = bars([0.0] * 300, "book_imb")
    for name in SIGNALS:
        s = signal_series(name, rows, W=50, p_lo=0.2, p_hi=0.8)
        assert len(s) == len(rows), name
        assert set(s) <= {"long", "short", None}, name


def test_book_imbalance_extreme_gives_direction():
    vals = [0.0] * 200 + [0.9]            # son bar aşırı alış ağırlıklı
    s = signal_series("book_imb", bars(vals, "book_imb"), W=100, p_lo=0.2, p_hi=0.8)
    assert s[-1] == "long"
    vals2 = [0.0] * 200 + [-0.9]
    assert signal_series("book_imb", bars(vals2, "book_imb"), W=100, p_lo=0.2, p_hi=0.8)[-1] == "short"


def test_no_signal_before_the_window_is_full():
    s = signal_series("book_imb", bars([0.1 * i for i in range(30)], "book_imb"), W=100, p_lo=0.2, p_hi=0.8)
    assert all(x is None for x in s)


def test_missing_values_produce_no_signal():
    rows = bars([None] * 300, "book_imb")
    assert all(x is None for x in signal_series("book_imb", rows, W=50, p_lo=0.2, p_hi=0.8))


def test_open_interest_signal_uses_change_not_level():
    """Seviye değil değişim: sürekli artan OI'de her bar sinyal vermemeli."""
    rows = bars([100 + i for i in range(300)], "open_interest")
    s = signal_series("oi_change", rows, W=100, p_lo=0.2, p_hi=0.8)
    assert sum(1 for x in s if x) < len(rows) // 2


def test_taker_ratio_signal_is_contrarian_at_extremes():
    vals = [1.0] * 200 + [5.0]            # aşırı alıcı baskısı → tükenme hipotezi: short
    s = signal_series("taker_ls", bars(vals, "taker_ls_ratio"), W=100, p_lo=0.2, p_hi=0.8)
    assert s[-1] == "short"


def test_unknown_signal_name_is_rejected():
    import pytest
    with pytest.raises(KeyError):
        signal_series("boyle-bir-sinyal-yok", bars([0.0] * 10, "book_imb"), W=5, p_lo=0.2, p_hi=0.8)


def test_scan_accepts_a_signal_source_instead_of_states(tmp_path):
    """Tarama, S1–S4 yerine yeni sinyalleri de aynı karar kuralıyla ölçebilmeli."""
    import json
    import random
    from scripts import barrier_scan

    rng = random.Random(9)
    px, rows = 100.0, []
    for i in range(2500):
        px *= 1 + rng.gauss(0, 0.001)
        rows.append({"symbol": "X", "start_ms": i * M, "end_ms": (i + 1) * M, "open": px,
                     "high": px * 1.002, "low": px * 0.998, "close": px, "volume": 1.0,
                     "buy_volume": 0.5, "trades": 3, "spread_bps": 1.0,
                     "book_imb": rng.uniform(-1, 1), "depth_usdt": 1e6,
                     "open_interest": 1000 + i, "taker_ls_ratio": rng.uniform(0.5, 2.0),
                     "account_ls_ratio": 1.0, "toptrader_ls_ratio": 1.0})
    f = tmp_path / "bars.jsonl"
    f.write_text("".join(json.dumps(r) + "\n" for r in rows))
    cfg = tmp_path / "research.toml"
    cfg.write_text('[bars]\nbar_ms=60000\n[features]\nW=60\nN_short=5\nN_long=15\n[states]\np_lo=0.2\np_hi=0.8\n'
                   '[horizons]\nminutes=[1]\n[costs]\nscenarios=[{name="taker/taker",fee_in_pct=0.05,fee_out_pct=0.05}]\n'
                   '[sampling]\ndiscovery_frac=0.7\nmin_n=10\n[bootstrap]\nn_boot=40\nseed=1\nalpha=0.05\n')
    out = tmp_path / "out.json"
    barrier_scan.main([str(f), "--config", str(cfg), "--tf", "1", "--stride", "5", "--signal", "book_imb",
                       "--screen-boot", "20", "--top", "2", "--json-out", str(out)])
    d = json.loads(out.read_text())
    assert d["signal"] == "book_imb"
    assert {r["dir"] for r in d["rows"]} <= {"long", "short"}
    assert d["rows"], "sinyalden hiç giriş üretilmedi"
