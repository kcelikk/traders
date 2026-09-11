import json
from pathlib import Path

from fbot.api.server import assemble_config, parse_latency_md, recorder_files


def test_parse_latency_md():
    md = """# x
| Seri | n | p50 | p95 | p99 | min | max | ort |
|---|---|---|---|---|---|---|---|
| keep-alive RTT | 1816 | 263 | 447 | 718 | 256 | 1526 | 293.0 |
| btcusdt@bookTicker: recv − E | 120761 | 142 | 325 | 431 | 138 | 7142 | 167.3 |
| istek → cevap RTT | 790 | 277 | 283 | 286 | 271 | 767 | 278.1 |
| clock skew (server − local orta nokta) | 1816 | 0.5 | 63.5 | 191.0 | -172.0 | 486.0 | 9.1 |
"""
    r = parse_latency_md(md)
    assert r["rest_rtt"]["p50"] == 263 and r["rest_rtt"]["p99"] == 718
    assert r["ws_public_lag"]["p99"] == 431 and r["wsapi_rtt"]["p50"] == 277 and r["skew"]["p99"] == 191.0


def test_recorder_files_lists_sizes(tmp_path):
    (tmp_path / "events-20260910T0800-1.jsonl.gz").write_bytes(b"x" * 1000)
    (tmp_path / "manifest.jsonl").write_text("{}\n")
    files = recorder_files(tmp_path)
    assert files[0]["name"].startswith("events-") and files[0]["size"] == 1000


def test_assemble_config_reads_tomls(tmp_path):
    (tmp_path / "recorder.toml").write_text('[run]\nout_dir="d"\nrotate_minutes=60\nsnapshot_interval_s=600\ntick_ms=1000\n[universe]\nmode="top"\ntop_n=10\n[streams]\npublic=["a"]\nmarket=["b"]\n[staleness_s]\npublic=30\nmarket=30\n[reconnect]\nbackoff_initial_s=1.0\nbackoff_max_s=30.0\n')
    (tmp_path / "research.toml").write_text('[bars]\nbar_ms=60000\n[features]\nW=240\nN_short=5\nN_long=15\n[states]\np_lo=0.2\np_hi=0.8\n[horizons]\nminutes=[1,5]\n[costs]\nscenarios=[]\n[sampling]\ndiscovery_frac=0.7\nmin_n=100\n[bootstrap]\nn_boot=10\nseed=1\nalpha=0.05\n')
    c = assemble_config(tmp_path)
    assert c["staleness_s"]["public"] == 30 and c["research"]["W"] == 240
    assert c["position"] == {} and c["risk"] == {}   # koşu kaydı verilmediyse eşikler boş kalır (F02)


def _api(tmp_path):
    from fbot.api.server import Api
    (tmp_path / "rec").mkdir()
    return Api(tmp_path / "rec", Path("ui"), history_files=0)


def test_state_carries_freshness_and_per_env_kill(tmp_path):
    api = _api(tmp_path)
    st = api.state()
    assert st["freshness"]["status"] in ("loading", "no_data", "stale", "live")
    assert set(st["kills"]) == {"paper", "testnet", "live"}
    assert len({k["path"] for k in st["kills"].values()}) == 3


def test_config_has_no_hardcoded_position_defaults(tmp_path):
    api = _api(tmp_path)
    c = api.state()["config"]
    assert c["position"] == {} and c["risk"] == {}          # koşu config yazmamışsa boş; uydurma değer yok
    assert c["source"].startswith("yok")


def test_assemble_config_uses_run_config_when_given(tmp_path):
    (tmp_path / "recorder.toml").write_text("[staleness_s]\npublic=30\n")
    (tmp_path / "research.toml").write_text("[features]\nW=240\n[states]\np_lo=0.2\np_hi=0.8\n[horizons]\nminutes=[1]\n[bootstrap]\nseed=7\n")
    c = assemble_config(tmp_path, {"core": {"risk": {"beta_cap_usdt": "750"}, "position": {"t_protect_ms": 3000}}, "git_sha": "abc"})
    assert c["risk"]["beta_cap_usdt"] == "750" and c["position"]["t_protect_ms"] == 3000
    assert c["run"]["git_sha"] == "abc" and c["source"] == "koşu kaydı"
