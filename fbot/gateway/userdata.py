"""User data stream: listenKey yaşam döngüsü + private bağlantı. I/O kenarı (ADR 0003).

Keepalive **bu yöneticinin parçasıdır**; başka bir yerde ayrı bir keepalive döngüsü yazılmaz
(CLAUDE.md yasağı, ADR 0003). Bağlantı yönetimi `CategoryConnection`'dan gelir: backoff,
`force_reconnect` ve ctrl olayları yeniden kullanılır, private için ikinci bir sınıf yazılmaz.

Akış: key al → bağlan → periyodik keepalive → `listenKeyExpired` ya da keepalive hatası →
yeni key + yeniden bağlan → mutabakat isteği (`on_resync`).

**Shadow modu (Gate 3 varsayılanı):** çerçeveler yalnız kayda yazılır, çekirdek tüketmez.
Amaç, canlı testnet servisinde gerçek veriyle bir gün gözlem yapmak; ayrı bir kurulum yok.

Gizlilik: listenKey bir kimlik bilgisidir. Kayda, log'a ve ctrl olayına **maskeli** girer.
"""
from __future__ import annotations

import asyncio
import json
import random
import time

from fbot.gateway.ws_category import CategoryConnection

# Binance: listenKey ömrü 60 dk, keepalive 30 dk önerilir (docs/binance-api-verification.md §12)
KEEPALIVE_S = 1800
EXPIRED_CODE = -1125          # "This listenKey does not exist"


def mask(key: str) -> str:
    return f"…{key[-4:]}" if key and len(key) > 4 else ""


class UserDataConnection:
    """`get_key()` ve `keepalive()` bloklayan REST çağrılarıdır; thread'e taşınarak çağrılır."""

    def __init__(self, *, base_url: str, get_key, keepalive, on_frame, on_ctrl,
                 keepalive_s: float = KEEPALIVE_S, jitter_s: float = 60.0, seed: int = 0,
                 backoff_initial_s: float = 1.0, backoff_max_s: float = 30.0, name: str = "private"):
        self.base_url = base_url.rstrip("/")
        self._get_key = get_key
        self._keepalive = keepalive
        self.on_frame = on_frame
        self.on_ctrl = on_ctrl
        self.keepalive_s = keepalive_s
        self.jitter_s = jitter_s
        self._rng = random.Random(seed)          # seed config'ten: rastlantı deterministik (Rule Zero #5)
        self.key: str | None = None
        self.last_frame_mono_ns = 0
        self.stats = {"keys": 0, "keepalives": 0, "keepalive_errors": 0, "expired": 0, "frames": 0}
        self._stop = asyncio.Event()
        self.conn = CategoryConnection(name, "", self._on_frame, on_ctrl,
                                       backoff_initial_s=backoff_initial_s, backoff_max_s=backoff_max_s,
                                       url_factory=self._url)

    # ---- kimlik
    async def _url(self) -> str:
        """Her bağlanmada yeni key alınır: eski key geçersizse tekrar bağlanmak işe yaramaz."""
        self.key = await asyncio.to_thread(self._get_key)
        self.stats["keys"] += 1
        self.on_ctrl("listen_key", {"key": mask(self.key), "n": self.stats["keys"]})
        return f"{self.base_url}/ws/{self.key}"

    def _on_frame(self, raw: bytes, recv_ns: int, mono_ns: int) -> None:
        self.stats["frames"] += 1
        self.last_frame_mono_ns = mono_ns
        if _is_expired(raw):
            self.stats["expired"] += 1
            self.on_ctrl("listen_key_expired", {"key": mask(self.key or "")})
            asyncio.get_running_loop().create_task(self._resync("listenKeyExpired"))
        self.on_frame(raw, recv_ns, mono_ns)

    async def _resync(self, reason: str) -> None:
        """Key geçersiz: bağlantıyı kapat (döngü yeni key ile yeniden bağlanır) ve mutabakat istenir."""
        await self.conn.force_reconnect(reason)

    # ---- keepalive (bu yöneticinin parçası; ayrı döngü yazılmaz)
    async def _keepalive_task(self) -> None:
        while not self._stop.is_set():
            wait = self.keepalive_s + self._rng.uniform(-self.jitter_s, self.jitter_s)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(1.0, wait))
                return
            except asyncio.TimeoutError:
                pass
            if self.key is None:
                continue
            try:
                await asyncio.to_thread(self._keepalive)
                self.stats["keepalives"] += 1
                self.on_ctrl("listen_key_keepalive", {"key": mask(self.key), "n": self.stats["keepalives"]})
            except Exception as e:  # noqa: BLE001 — hata YUTULMAZ: kayda geçer ve yeniden bağlanılır
                self.stats["keepalive_errors"] += 1
                self.on_ctrl("listen_key_keepalive_error", {"err": repr(e)[:200], "key": mask(self.key)})
                await self._resync("keepalive_error")

    async def run(self) -> None:
        await asyncio.gather(self.conn.run(), self._keepalive_task())

    def stop(self) -> None:
        self._stop.set()
        self.conn.stop()

    def age_s(self, now_mono_ns: int | None = None) -> float | None:
        """Private akış bayatlığı market bayatlığından ayrı izlenir: sessiz bir user stream normaldir
        (emir yoksa olay da yok), ama saatlerce sessizlik kopmuş bağlantı demektir."""
        if self.last_frame_mono_ns == 0:
            return None
        return ((now_mono_ns or time.monotonic_ns()) - self.last_frame_mono_ns) / 1e9


def _is_expired(raw: bytes) -> bool:
    if b"listenKeyExpired" not in raw:
        return False
    try:
        return json.loads(raw).get("e") == "listenKeyExpired"
    except ValueError:
        return False
