"""Strateji platformu (Gate 5): manifest, terfi zinciri, kayıt defteri, ilk plugin.

Gate çıkış koşulu paritedir: plugin üzerinden koşan mantık, gömülü hâliyle **bit-eşit** niyet
üretmeli. Soyutlama davranışı değiştirmemeli.
"""
from decimal import Decimal as D

import pytest

from fbot.core.decision import Cell, DecisionConfig, decide_explain
from fbot.strategy.base import StrategyContext
from fbot.strategy.manifest import ManifestError, StrategyManifest, parse_manifest
from fbot.strategy.registry import RegistryError, StrategyRegistry
from fbot.strategy.v1_state_cell import StateCellStrategy

CELLS = (Cell(state="S1", dir="long", h=15),)
DCFG = DecisionConfig(allowed_cells=CELLS, notional_usdt=D("80"), max_state_age_bars=3, spread_mult=D("2"),
                      research_spread_bps={"BTCUSDT": D("1.0")}, funding_guard_ms=120_000,
                      sl_pct={"S1": D("0.5")}, tp_pct={"S1": D("1.0")}, report_hash="a693aa07")
MANIFEST = {"id": "v1_state_cell", "version": "1.0", "allowed_modes": ["replay", "paper"],
            "promotion_state": "replay_ok", "required_streams": ["aggTrade"]}


def view(**kw):
    base = dict(symbol="BTCUSDT", state="S1", age_bars=1, features={"ret_long": 1.0},
                best_bid=D("77990"), best_ask=D("78010"), spread_bps=D("1.2"), stale=False,
                now_ms=1_000_000, next_funding_ms=9_000_000, bar_end_ms=999_000, has_position=False)
    base.update(kw)
    return base


# ---- manifest ve terfi zinciri
def test_manifest_requires_identity():
    with pytest.raises(ManifestError, match="id"):
        parse_manifest({"version": "1.0"})
    with pytest.raises(ManifestError, match="version"):
        parse_manifest({"id": "x"})


def test_live_permission_requires_a_completed_promotion_chain():
    """Fail-closed: canlı izni terfi tamamlanmadan verilemez."""
    with pytest.raises(ManifestError, match="live"):
        parse_manifest({**MANIFEST, "allowed_modes": ["live"], "promotion_state": "testnet_ok"})
    m = parse_manifest({**MANIFEST, "allowed_modes": ["live"], "promotion_state": "live"})
    assert m.may_run("live") is None


def test_promotion_state_gates_each_mode():
    m = parse_manifest({**MANIFEST, "allowed_modes": ["replay", "paper", "testnet"],
                        "promotion_state": "replay_ok"})
    assert m.may_run("replay") is None
    assert m.may_run("paper") is None                      # replay_ok paper için yeterli
    assert "paper_ok" in m.may_run("testnet")              # testnet için yetmez


def test_mode_not_in_allowed_modes_is_refused_with_a_reason():
    m = parse_manifest(MANIFEST)
    why = m.may_run("testnet")
    assert why and "allowed_modes" in why


def test_unknown_promotion_or_mode_is_an_error():
    with pytest.raises(ManifestError):
        parse_manifest({**MANIFEST, "promotion_state": "harika"})
    with pytest.raises(ManifestError):
        parse_manifest({**MANIFEST, "allowed_modes": ["mainnet"]})


# ---- kayıt defteri
def registry(mode="paper"):
    return StrategyRegistry(mode=mode)


def test_registry_blocks_instead_of_silently_skipping():
    """İki ayrı engel, iki ayrı gerekçe: moda yetkili değil ya da terfi yetmiyor."""
    r = registry(mode="testnet")
    r.register(parse_manifest(MANIFEST), StateCellStrategy(DCFG), code_hash="abc")
    assert r.active() == [] and "allowed_modes" in r.blocked["v1_state_cell"]

    r2 = registry(mode="testnet")
    r2.register(parse_manifest({**MANIFEST, "allowed_modes": ["replay", "paper", "testnet"]}),
                StateCellStrategy(DCFG), code_hash="abc")
    assert r2.active() == [] and "paper_ok" in r2.blocked["v1_state_cell"]


def test_registry_accepts_a_permitted_strategy_and_stamps_the_code_hash():
    r = registry()
    r.register(parse_manifest(MANIFEST), StateCellStrategy(DCFG), code_hash="abc123")
    assert [x.id for x in r.active()] == ["v1_state_cell"]
    assert r.get("v1_state_cell").code_hash == "abc123"
    assert r.view()["active"][0]["promotion"] == "replay_ok"


def test_version_mismatch_between_manifest_and_code_is_refused():
    r = registry()
    with pytest.raises(RegistryError, match="sürüm"):
        r.register(parse_manifest({**MANIFEST, "version": "9.9"}), StateCellStrategy(DCFG), code_hash="abc")


def test_duplicate_id_is_refused():
    r = registry()
    r.register(parse_manifest(MANIFEST), StateCellStrategy(DCFG), code_hash="a")
    with pytest.raises(RegistryError, match="zaten kayıtlı"):
        r.register(parse_manifest(MANIFEST), StateCellStrategy(DCFG), code_hash="b")


# ---- parite: plugin gömülü mantıkla bit-eşit
def test_plugin_produces_the_same_intent_as_the_embedded_logic():
    """Gate 5 çıkış koşulu: soyutlama davranışı değiştirmemeli."""
    s = StateCellStrategy(DCFG)
    direct, _ = decide_explain(view(), DCFG)
    out = s.on_bar(StrategyContext(symbol="BTCUSDT", view=view(), now_ns=1, params={}))
    assert len(out) == 1 and out[0] == direct
    assert out[0].client_order_id == direct.client_order_id


def test_plugin_reports_why_no_intent_was_produced():
    s = StateCellStrategy(DCFG)
    assert s.on_bar(StrategyContext("BTCUSDT", view(state="S2"), 1, {})) == []
    assert s.last_block == "D1_hucre_yok"


def test_empty_allowed_cells_means_no_intent():
    """Kârlılık gösterilmedi (ADR 0010): boş hücre listesiyle strateji sessizdir."""
    s = StateCellStrategy(DecisionConfig(**{**DCFG.__dict__, "allowed_cells": ()}))
    assert s.on_bar(StrategyContext("BTCUSDT", view(), 1, {})) == []
    assert s.last_block == "allowed_cells_bos"


# ---- iki katmanlı risk: strateji bütçesi global limitlerin altında
def risk_inputs(**kw):
    from fbot.core.position import Filters
    from fbot.core.risk import RiskInputs
    base = dict(kill_switch=False, reconciled=True, warmup_bars={"BTCUSDT": 999}, stale={},
                skew_ms=0, open_positions={}, pending_entries=set(), gross_usdt=D(0),
                beta_exposure_usdt=D(0), betas={}, account_leverage={"BTCUSDT": 10},
                available_balance=D("10000"),
                filters={"BTCUSDT": Filters(D("0.001"), D("0.001"), D("5"), D("0.1"))},
                spread_bps={"BTCUSDT": D("1")}, depth_notional={}, slippage_bps={"BTCUSDT": D(0)},
                last_exit_ms={}, last_exit_was_loss={}, last_stp_ms={}, orders_left_10s=100,
                orders_left_1m=500, last_429_ms=None, banned=False, now_ms=1_000_000)
    base.update(kw)
    return RiskInputs(**base)


def intent():
    from fbot.core.risk import EntryIntent
    return EntryIntent(symbol="BTCUSDT", side="long", notional=D("80"), price=D("78000"),
                       reduce_only=False, entry_state="S1")


def risk_cfg(**kw):
    from fbot.core.risk import RiskConfig
    base = dict(max_positions=5, gross_cap_usdt=D("400"), beta_cap_usdt=None, leverage={"BTCUSDT": 10},
                default_leverage=5, margin_buffer=D("0.2"), spread_max_bps=D("50"),
                participation_max=None, slippage_max_bps=None, cooldown_ms=None, cooldown_loss_ms=None,
                cooldown_stp_ms=None, reserve_orders=3, backoff_ms=10_000, skew_max_ms=None, warmup_bars=0)
    base.update(kw)
    return RiskConfig(**base)


def test_strategy_budget_rejects_below_the_global_limit():
    """İki katman: strateji bütçesi global limitlerin altında ikinci bir kapıdır."""
    from fbot.core.risk import assess

    v = assess(intent(), risk_inputs(strategy_budget={"max_positions": 1}, strategy_open=1), risk_cfg())
    assert v.kind == "REJECT" and "K19_strategy_max_positions" in v.reasons


def test_global_limit_still_wins_when_the_strategy_budget_is_generous():
    from fbot.core.risk import assess

    v = assess(intent(), risk_inputs(strategy_budget={"max_positions": 99},
                                     open_positions={f"p{i}": f"S{i}USDT" for i in range(5)}), risk_cfg())
    assert v.kind == "REJECT" and "K6_max_positions" in v.reasons


def test_strategy_gross_cap_resizes_like_the_global_one():
    """Bütçe kalanı işlem büyüklüğünün altındaysa küçültülür — global `gross_cap` ile aynı mekanik."""
    from fbot.core.risk import assess

    v = assess(intent(), risk_inputs(strategy_budget={"gross_cap_usdt": "200"}, strategy_gross_usdt=D("121")),
               risk_cfg())
    assert "K19_strategy_gross_cap" in v.reasons and v.kind == "RESIZE" and v.qty == D("0.001")


def test_strategy_budget_leftover_below_the_lot_size_is_a_rejection_not_a_dust_order():
    """Kalan 40 USDT, 78.000'lik fiyatta 0,001 adımın altına düşer: filtre reddeder (fail-closed)."""
    from fbot.core.risk import assess

    v = assess(intent(), risk_inputs(strategy_budget={"gross_cap_usdt": "100"}, strategy_gross_usdt=D("60")),
               risk_cfg())
    assert v.kind == "REJECT" and "K12_filters" in v.reasons and v.qty is None


def test_lease_owned_by_another_strategy_marks_the_symbol_busy():
    from fbot.core.risk import assess

    v = assess(intent(), risk_inputs(lease_busy="baska_strateji:v2"), risk_cfg())
    assert v.kind == "REJECT" and any(r.startswith("K7_symbol_busy") for r in v.reasons)


def test_no_budget_and_no_lease_leaves_behaviour_unchanged():
    """Tek strateji hâlinde yeni alanlar etkisizdir: Gate 4 davranışı korunur."""
    from fbot.core.risk import assess

    v = assess(intent(), risk_inputs(), risk_cfg())
    assert v.kind == "APPROVE" and not [r for r in v.reasons if r.startswith(("K19", "K7"))]


# ---- kapının fail-closed olması: engellenen strateji gömülü motora düşmemeli
def test_blocked_registry_does_not_fall_back_to_the_embedded_engine():
    """Aksi hâlde terfi kapısı anlamsız olurdu: aynı mantık kapıyı atlayarak çalışırdı."""
    import json

    from fbot.core.engine import CoreConfig, CoreState, Engine
    from fbot.core.risk import RiskConfig
    from fbot.core.state_engine import StateEngineConfig
    from fbot.events import RawEvent

    reg = StrategyRegistry(mode="testnet")      # manifest yalnız replay/paper'a izin veriyor
    reg.register(parse_manifest(MANIFEST), StateCellStrategy(DCFG), code_hash="abc")
    assert reg.active() == []

    cfg = CoreConfig(bar_ms=60_000, staleness_ms={"public": 30_000, "market": 30_000},
                     state_engine=StateEngineConfig(W=5, N_short=2, N_long=3, p_lo=0.2, p_hi=0.8),
                     decision=DCFG,
                     risk=RiskConfig(max_positions=5, gross_cap_usdt=None, beta_cap_usdt=None, leverage={},
                                     default_leverage=5, margin_buffer=D("0.2"), spread_max_bps=None,
                                     participation_max=None, slippage_max_bps=None, cooldown_ms=None,
                                     cooldown_loss_ms=None, cooldown_stp_ms=None, reserve_orders=3,
                                     backoff_ms=10_000, skew_max_ms=None, warmup_bars=0),
                     strategies=reg)
    eng = Engine(cfg)
    intent, blocked, _ = eng._intent_from(view(), now_ns=1, default_id="v1_state_cell")
    assert intent is None and blocked == "strateji_yetkili_degil"


def test_registry_with_an_active_strategy_produces_the_intent():
    from fbot.core.engine import CoreConfig, Engine

    reg = StrategyRegistry(mode="paper")
    reg.register(parse_manifest(MANIFEST), StateCellStrategy(DCFG), code_hash="abc")
    eng = Engine(CoreConfig(bar_ms=60_000, staleness_ms={}, decision=DCFG, strategies=reg))
    intent, blocked, sid = eng._intent_from(view(), now_ns=1, default_id="x")
    assert intent is not None and blocked is None and sid == "v1_state_cell"


def test_parity_between_the_embedded_path_and_the_plugin_path():
    """Gate 5 çıkış koşulu: aynı senaryo, aynı komut dizisi (bit-eşit)."""
    from scripts.parity_check import scenario_parity

    r = scenario_parity()
    assert r["esit"] is True and r["ilk_fark"] is None
    assert r["gomulu"]["hash"] == r["plugin"]["hash"] and r["gomulu"]["komut"] > 0


def test_every_enabled_strategy_has_a_manifest_on_disk(repo_root):
    """Canlıda yakalanan hata: manifest image'a kopyalanmıyordu ve servis açılışta düştü."""
    import tomllib

    for cfg_name in ("testnet.toml", "paper.toml", "paper-demo.toml"):
        cfg = tomllib.loads((repo_root / "config" / cfg_name).read_bytes().decode())
        for sid in (cfg.get("strategy") or {}).get("enabled", []):
            path = repo_root / "strategies" / sid / "manifest.toml"
            assert path.exists(), f"{cfg_name}: {sid} manifest'i yok ({path})"
            m = parse_manifest(tomllib.loads(path.read_bytes().decode()))
            assert m.id == sid


def test_dockerfile_ships_the_strategies_directory(repo_root):
    text = (repo_root / "docker" / "Dockerfile").read_text()
    assert "COPY strategies" in text, "manifest dizini image'a kopyalanmazsa servis açılışta düşer"
