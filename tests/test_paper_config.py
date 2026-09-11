import pytest

from fbot.paper.config import PaperConfigError, load_paper_config


def test_loads_real_config():
    cfg, h = load_paper_config("config/paper.toml")
    assert cfg.recorder.top_n == 10 and cfg.recorder.tick_ms == 1000
    assert cfg.core.state_engine.W == 240 and cfg.core.state_engine.p_hi == 0.8
    assert cfg.core.position.working_type == "MARK_PRICE" and cfg.core.position.degrade_map == {"S1": {"S2"}, "S2": {"S1"}}
    assert cfg.core.risk.warmup_bars == 480 and cfg.core.risk.gross_cap_usdt is not None
    assert cfg.core.decision.allowed_cells == ()          # Faz 3: geçen hücre yok
    assert cfg.core.decision.sl_pct == {} and cfg.core.decision.tp_pct == {}
    assert cfg.sim_latency_ms == 400 and cfg.sim_seed == 20260910
    assert len(h) == 12


def test_allowed_cells_require_sl_tp(tmp_path):
    src = open("config/paper.toml").read().replace("allowed_cells = []", 'allowed_cells = [{ state = "S1", dir = "long", h = 15 }]')
    p = tmp_path / "p.toml"; p.write_text(src)
    with pytest.raises(PaperConfigError, match="sl_pct"):
        load_paper_config(p)


def test_leverage_must_match_locked_decision(tmp_path):
    src = open("config/paper.toml").read().replace("leverage = { BTCUSDT = 10, ETHUSDT = 10 }", "leverage = { BTCUSDT = 20 }")
    p = tmp_path / "p.toml"; p.write_text(src)
    with pytest.raises(PaperConfigError, match="kaldıraç"):
        load_paper_config(p)


def test_sim_params_loaded():
    cfg, _ = load_paper_config("config/paper.toml")
    assert cfg.sim_jitter_ms == 600 and cfg.sim_partial_timeout_ms == 5000
    assert cfg.sim_prob_fill_on_touch == 0.0 and cfg.sim_book_levels == 20


def test_testnet_config_loads_and_is_narrow():
    cfg, _ = load_paper_config("config/testnet.toml")
    assert cfg.recorder.mode == "list" and cfg.recorder.symbols == ["BTCUSDT", "ETHUSDT"]
    assert cfg.core.risk.max_positions == 2 and str(cfg.core.risk.gross_cap_usdt) == "160"
    assert str(cfg.core.risk.beta_cap_usdt) == "750"
    assert cfg.core.decision.allowed_cells == ()       # strateji yok → emir yok
    assert cfg.core.account.get("paper") is False      # kaldıraç borsadan


def test_cost_drift_config_loaded():
    cfg, _ = load_paper_config("config/paper.toml")
    assert cfg.cost_drift is not None and cfg.cost_drift.window_ms == 86_400_000
    assert str(cfg.cost_drift.net_per_trade_min) == "-0.05" and cfg.cost_drift.min_trades == 20
