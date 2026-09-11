"""Etkin yapılandırmanın serileştirilmesi — konsol sabit değer değil gerçek config göstermek zorunda (F02)."""
from decimal import Decimal

from fbot.paper.config import load_paper_config
from fbot.paper.config_view import effective_config


def test_effective_config_serializes_nested_dataclasses_and_decimals():
    cfg, h = load_paper_config("config/paper.toml")
    d = effective_config(cfg)
    assert isinstance(d["core"]["position"]["t_protect_ms"], int)
    assert isinstance(d["core"]["risk"]["max_positions"], int)
    # Decimal ve None alanlar JSON'a uygun hale gelir
    import json
    json.dumps(d)
    assert d["sim_seed"] == cfg.sim_seed


def test_effective_config_keeps_decimal_as_string():
    from dataclasses import dataclass

    @dataclass
    class X:
        a: Decimal
        b: object

    assert effective_config(X(Decimal("0.30"), None)) == {"a": "0.30", "b": None}


def test_effective_config_handles_lists_and_sets():
    from dataclasses import dataclass

    @dataclass
    class Y:
        items: list
        tags: frozenset

    out = effective_config(Y([Decimal("1"), 2], frozenset({"b", "a"})))
    assert out["items"] == ["1", 2] and out["tags"] == ["a", "b"]
