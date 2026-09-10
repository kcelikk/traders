"""Faz 6 zinciri: bar → durum → karar → risk → pozisyon. Çekirdekte, saf, deterministik."""
import json
from decimal import Decimal

from fbot.core.commands import PlaceAlgo, PlaceOrder, StateChanged, canonical
from fbot.core.decision import Cell, DecisionConfig
from fbot.core.engine import CoreConfig, CoreState, Engine
from fbot.core.position import Filters, PositionConfig
from fbot.core.risk import RiskConfig
from fbot.core.state_engine import StateEngineConfig
from fbot.events import RawEvent

SE = StateEngineConfig(W=5, N_short=2, N_long=3, p_lo=0.2, p_hi=0.8)
FILT = {"XUSDT": Filters(Decimal("0.001"), Decimal("0.001"), Decimal("5"), Decimal("0.01"))}
PCFG = PositionConfig(t_protect_ms=3000, t_backup_ms=1500, working_type="MARK_PRICE", price_protect=True,
                      min_replace_interval_ms=5000, taker_fee_pct=Decimal("0.05"), maker_fee_pct=Decimal("0.02"))
RCFG = RiskConfig(max_positions=5, gross_cap_usdt=Decimal("400"), beta_cap_usdt=None, leverage={}, default_leverage=5,
                  margin_buffer=Decimal("0.2"), spread_max_bps=Decimal("50"), participation_max=None, slippage_max_bps=None,
                  cooldown_ms=None, cooldown_loss_ms=None, cooldown_stp_ms=None, reserve_orders=3, backoff_ms=10_000,
                  skew_max_ms=None, warmup_bars=0)


def cfg(cells, **kw):
    dcfg = DecisionConfig(allowed_cells=cells, notional_usdt=Decimal("80"), max_state_age_bars=None, spread_mult=Decimal("10"),
                          research_spread_bps={"XUSDT": Decimal("5")}, funding_guard_ms=None,
                          sl_pct={s: Decimal("0.5") for s in "S1 S2 S3 S4".split()}, tp_pct={s: Decimal("1.0") for s in "S1 S2 S3 S4".split()},
                          report_hash="test")
    base = dict(bar_ms=60_000, staleness_ms={"market": 30_000, "public": 30_000}, position=PCFG, filters=FILT, tick_ms=1000,
                state_engine=SE, decision=dcfg, risk=RCFG, account={"available_balance": "1000", "leverage": {"XUSDT": 5}})
    base.update(kw)
    return CoreConfig(**base)


def stream(n=90):
    out = []
    for i in range(1, n):
        px = 100 + (i % 11) - 5
        out.append(("market", "xusdt@aggTrade", {"e": "aggTrade", "s": "XUSDT", "a": i, "p": str(px), "q": "1", "T": i * 60_000, "E": 1, "m": i % 3 == 0}))
        out.append(("public", "xusdt@bookTicker", {"e": "bookTicker", "s": "XUSDT", "u": i, "b": str(px - 0.01), "B": "5", "a": str(px + 0.01), "A": "5", "E": 1}))
        out.append(("market", "xusdt@markPrice@1s", {"e": "markPriceUpdate", "s": "XUSDT", "p": str(px), "r": "0.0001", "T": 10**12, "E": 1}))
    return out


def run(c, evs):
    eng, st = Engine(c), CoreState()
    t = 10**12
    allc = []
    for i, (cat, s, d) in enumerate(evs, 1):
        raw = json.dumps({"stream": s, "data": d}).encode()
        st, cmds = eng.step(st, RawEvent(i, t + i * 10**6, i, cat, s, raw), t + i * 10**6)
        allc += cmds
    return st, allc


def test_no_allowed_cells_means_no_orders():
    st, cmds = run(cfg(()), stream())
    assert [c for c in cmds if isinstance(c, StateChanged)]           # durumlar üretiliyor
    assert not [c for c in cmds if isinstance(c, (PlaceOrder, PlaceAlgo))]   # ama emir yok
    assert st.intents_rejected == 0 and st.intents_made == 0


def test_allowed_cell_produces_entry_order_then_protection():
    labels = {c.to_state for c in run(cfg(()), stream())[1] if isinstance(c, StateChanged)}
    cells = tuple(Cell(state=s, dir=d, h=15) for s in labels - {"S0"} for d in ("long", "short"))
    st, cmds = run(cfg(cells), stream())
    entries = [c for c in cmds if isinstance(c, PlaceOrder) and not c.reduce_only]
    assert entries, "giriş emri üretilmedi"
    e = entries[0]
    assert e.symbol == "XUSDT" and e.client_id.startswith("eXUSDT") and e.qty > 0
    assert st.intents_made >= 1
    # emir dolduğunda koruma emirleri gelir
    eng, st2 = Engine(cfg(cells)), CoreState()
    fill = RawEvent(1, 10**12, 1, "exec", "entry_fill", json.dumps({"pos_id": "p1", "symbol": "XUSDT", "side": "long", "price": "100", "qty": "0.8", "sl": "99.5", "tp": "101"}).encode())
    st2, c2 = eng.step(st2, fill, 10**12)
    assert [type(x) for x in c2] == [PlaceAlgo, PlaceAlgo]


def test_risk_veto_blocks_entry_and_is_counted():
    labels = {c.to_state for c in run(cfg(()), stream())[1] if isinstance(c, StateChanged)}
    cells = tuple(Cell(state=s, dir=d, h=15) for s in labels - {"S0"} for d in ("long", "short"))
    c = cfg(cells, account={"available_balance": "0", "leverage": {"XUSDT": 5}})   # K11 teminat
    st, cmds = run(c, stream())
    assert not [x for x in cmds if isinstance(x, PlaceOrder) and not x.reduce_only]
    assert st.intents_rejected >= 1
    assert any("K11_margin" in r for r in st.last_verdicts[0]["reasons"])


def test_pipeline_is_deterministic():
    labels = {c.to_state for c in run(cfg(()), stream())[1] if isinstance(c, StateChanged)}
    cells = tuple(Cell(state=s, dir=d, h=15) for s in labels - {"S0"} for d in ("long", "short"))
    a = [canonical(c) for c in run(cfg(cells), stream())[1]]
    b = [canonical(c) for c in run(cfg(cells), stream())[1]]
    assert a == b and len(a) > 0


def test_entry_fill_uses_intent_sl_tp_and_clears_pending():
    """Dolum olayı sl/tp taşımasa da intent'ten (yüzdeden) türetilir; pending temizlenir."""
    labels = {c.to_state for c in run(cfg(()), stream())[1] if isinstance(c, StateChanged)}
    cells = tuple(Cell(state=s, dir=d, h=15) for s in labels - {"S0"} for d in ("long", "short"))
    c = cfg(cells)
    eng, st = Engine(c), CoreState()
    t = 10**12
    evs = stream()
    for i, (cat, s, d) in enumerate(evs, 1):
        raw = json.dumps({"stream": s, "data": d}).encode()
        st, cmds = eng.step(st, RawEvent(i, t + i * 10**6, i, cat, s, raw), t + i * 10**6)
        entry = next((x for x in cmds if isinstance(x, PlaceOrder) and not x.reduce_only), None)
        if entry:
            break
    assert entry and st.pending_entries == {"XUSDT"}
    fill = json.dumps({"client_id": entry.client_id, "symbol": "XUSDT", "price": "100", "qty": str(entry.qty)}).encode()
    st, cmds = eng.step(st, RawEvent(10**6, t + 10**9, 1, "exec", "entry_fill", fill), t + 10**9)
    algos = [x for x in cmds if isinstance(x, PlaceAlgo)]
    assert len(algos) == 2
    sl = next(a for a in algos if a.type == "STOP_MARKET")
    assert sl.trigger_price == Decimal("100") * (1 - Decimal("0.5") / 100)
    assert sl.close_position and sl.working_type == "MARK_PRICE"
    assert st.pending_entries == set()
    pos = list(st.positions.values())[0]
    assert pos.entry_state in labels and pos.symbol == "XUSDT"


def test_paper_account_assumes_config_leverage():
    """Paper'da borsa yok: kaldıraç görünümü config'ten gelmezse K10 her girişi reddeder."""
    labels = {c.to_state for c in run(cfg(()), stream())[1] if isinstance(c, StateChanged)}
    cells = tuple(Cell(state=s, dir=d, h=15) for s in labels - {"S0"} for d in ("long", "short"))
    c = cfg(cells, account={"available_balance": "1000", "paper": True})   # leverage yok
    st, cmds = run(c, stream())
    assert [x for x in cmds if isinstance(x, PlaceOrder) and not x.reduce_only], "paper hesabında K10 takıldı"
    assert not any("K10_leverage" in v["reasons"] for v in st.last_verdicts)


def test_all_verdicts_are_countable_not_capped():
    labels = {c.to_state for c in run(cfg(()), stream())[1] if isinstance(c, StateChanged)}
    cells = tuple(Cell(state=s, dir=d, h=15) for s in labels - {"S0"} for d in ("long", "short"))
    st, _ = run(cfg(cells, account={"available_balance": "0", "paper": True}), stream())
    assert st.verdicts_total == st.intents_rejected + st.intents_made
    assert st.verdicts_total > len(st.last_verdicts)      # liste kırpılır, sayaç kırpılmaz
    assert all("n" in v for v in st.last_verdicts)


def test_paper_account_assumes_config_leverage():
    """Paper'da borsa yok: kaldıraç görünümü config'ten gelmezse K10 her girişi reddeder."""
    labels = {c.to_state for c in run(cfg(()), stream())[1] if isinstance(c, StateChanged)}
    cells = tuple(Cell(state=s, dir=d, h=15) for s in labels - {"S0"} for d in ("long", "short"))
    c = cfg(cells, account={"available_balance": "1000", "paper": True})
    st, cmds = run(c, stream())
    assert [x for x in cmds if isinstance(x, PlaceOrder) and not x.reduce_only], "paper hesabında K10 takıldı"
    assert not any("K10_leverage" in v["reasons"] for v in st.last_verdicts)


def test_all_verdicts_are_countable_not_capped():
    labels = {c.to_state for c in run(cfg(()), stream())[1] if isinstance(c, StateChanged)}
    cells = tuple(Cell(state=s, dir=d, h=15) for s in labels - {"S0"} for d in ("long", "short"))
    st, _ = run(cfg(cells, account={"available_balance": "0", "paper": True}), stream())
    assert st.verdicts_total == st.intents_rejected + st.intents_made
    assert st.verdicts_total > len(st.last_verdicts)
    assert all("n" in v for v in st.last_verdicts)
