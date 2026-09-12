"""Recorder config: TOML (stdlib tomllib), doğrulama, içerik hash'i."""
from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(ValueError):
    pass


# Stream türü → şablonda aranan anahtar. Bilinmeyen şablon hata verir (sessizce düşürülmez).
STREAM_KINDS = ("bookTicker", "depth", "aggTrade", "markPrice", "forceOrder")

# Rol bazlı profiller: hangi sürecin hangi stream'e gerçekten ihtiyacı var.
#   recorder       — hepsi; araştırma girdisi budur, hiçbir şey kaybedilmez.
#   trader_paper   — depth gerekli: dolum simülatörünün girdisi (ADR 0013).
#   trader_testnet — depth gereksiz: execution gerçek borsada, simülatör yok (`_NullSim`).
# forceOrder hiçbir trader profilinde yok: çekirdek tüketmiyor (H9/H10 reddedildi).
STREAM_PROFILES = {
    "recorder": set(STREAM_KINDS),
    "trader_paper": {"bookTicker", "depth", "aggTrade", "markPrice"},
    "trader_testnet": {"bookTicker", "aggTrade", "markPrice"},
}


def stream_kind(template: str) -> str:
    for k in STREAM_KINDS:
        if k.lower() in template.lower():
            return k
    raise ConfigError(f"bilinmeyen stream şablonu: {template!r} (bilinenler: {', '.join(STREAM_KINDS)})")


def apply_profile(templates: list[str], profile: str) -> list[str]:
    """Profilin kapsamadığı stream'leri düşürür. Sıra korunur."""
    if profile not in STREAM_PROFILES:
        raise ConfigError(f"[streams] profile={profile!r} bilinmiyor (geçerli: {', '.join(sorted(STREAM_PROFILES))})")
    keep = STREAM_PROFILES[profile]
    return [t for t in templates if stream_kind(t) in keep]


@dataclass(frozen=True)
class RecorderConfig:
    out_dir: str
    rotate_minutes: int
    snapshot_interval_s: int
    mode: str
    top_n: int
    symbols: list[str]
    exclude_bases: frozenset[str]
    public_streams: list[str]
    market_streams: list[str]
    staleness_s: dict[str, float]
    backoff_initial_s: float
    backoff_max_s: float
    depth_snapshot_limit: int = 1000
    stats_interval_s: float = 10.0
    tick_ms: int = 1000
    profile: str = "recorder"      # rol bazlı stream kümesi; public/market listeleri buna göre süzülmüştür


def _need(d: dict, key: str, section: str):
    if key not in d:
        raise ConfigError(f"[{section}] '{key}' eksik")
    return d[key]


def load_recorder_config(path: str | Path) -> tuple[RecorderConfig, str]:
    data = Path(path).read_bytes()
    h = hashlib.sha256(data).hexdigest()[:12]
    try:
        t = tomllib.loads(data.decode())
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(str(e)) from e
    for sec in ("run", "universe", "streams", "staleness_s", "reconnect"):
        if sec not in t:
            raise ConfigError(f"[{sec}] bölümü eksik")
    run, uni, st, stale, rc = t["run"], t["universe"], t["streams"], t["staleness_s"], t["reconnect"]
    profile = st.get("profile", "recorder")
    mode = _need(uni, "mode", "universe")
    symbols = list(uni.get("symbols", []))
    if mode == "list" and not symbols:
        raise ConfigError("[universe] mode='list' için 'symbols' gerekli")
    if mode not in ("top", "list"):
        raise ConfigError("[universe] mode 'top' veya 'list' olmalı")
    cfg = RecorderConfig(
        out_dir=_need(run, "out_dir", "run"),
        rotate_minutes=int(_need(run, "rotate_minutes", "run")),
        snapshot_interval_s=int(_need(run, "snapshot_interval_s", "run")),
        mode=mode,
        top_n=int(uni.get("top_n", 0)),
        symbols=symbols,
        exclude_bases=frozenset(uni.get("exclude_bases", [])),
        public_streams=apply_profile(list(_need(st, "public", "streams")), profile),
        market_streams=apply_profile(list(_need(st, "market", "streams")), profile),
        staleness_s={k: float(v) for k, v in stale.items()},
        backoff_initial_s=float(_need(rc, "backoff_initial_s", "reconnect")),
        backoff_max_s=float(_need(rc, "backoff_max_s", "reconnect")),
        depth_snapshot_limit=int(run.get("depth_snapshot_limit", 1000)),
        stats_interval_s=float(run.get("stats_interval_s", 10.0)),
        tick_ms=int(run.get("tick_ms", 1000)),
        profile=profile,
    )
    return cfg, h
