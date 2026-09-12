"""Kalıcı HTTPS bağlantı havuzu (stdlib). I/O kenarı; `asyncio.to_thread` ile çağrılır.

Neden: bugün her REST isteği yeni bir `HTTPSConnection` açıyor (`fbot/gateway/rest.py`,
`fbot/gateway/testnet.py`), yani her emir bir TLS el sıkışması ödüyor. Ölçülen emir RTT'si
264 / 680 ms (p50/p99) ve bunun büyük kısmı bağlantı kurulumu.

ADR 0002 "ek HTTP kütüphanesi eklenmez" diyor; bu yüzden `aiohttp` yok, stdlib `http.client`
üstüne havuz var.

İki ayrı zaman aşımı: bağlanma ve okuma. Tek `timeout` ile 10 s'lik bir okuma beklemesi, bağlantı
kurulamadığı hâlde 10 s bloke olmak demekti.

**Kör retry yoktur.** POST tekrarlanmaz: sonucu bilinmeyen bir emir ikinci kez gönderilirse iki
pozisyon açılır (Gate 0 §5: aynı `clientOrderId` ile iki emir de kabul edildi ve ikisi de doldu).
Yalnızca `GET` (idempotent okuma) bir kez tekrarlanır ve yalnız bağlantı **yeniden kullanılmışken**
kopmuşsa: sunucu kapanmış bir keep-alive bağlantısını bu şekilde bildirir.
"""
from __future__ import annotations

import http.client
import socket
import threading
import time

RETRYABLE = (http.client.RemoteDisconnected, http.client.BadStatusLine, ConnectionResetError, BrokenPipeError)


class HTTPPool:
    """Tek host için tek kalıcı bağlantı. Tek yazar varsayımı: çağrılar kilit altında sıralanır."""

    def __init__(self, host: str, connect_timeout_s: float = 2.0, read_timeout_s: float = 5.0,
                 max_idle_s: float = 120.0, conn_factory=None, clock=time.monotonic):
        self.host = host
        self.connect_timeout_s = connect_timeout_s
        self.read_timeout_s = read_timeout_s
        self.max_idle_s = max_idle_s
        self._factory = conn_factory or (lambda h, t: http.client.HTTPSConnection(h, timeout=t))
        self._clock = clock
        self._lock = threading.Lock()
        self._conn = None
        self._last_use = 0.0
        self.stats = {"requests": 0, "connects": 0, "reused": 0, "retries": 0, "timeouts": 0, "errors": 0}

    # ---- bağlantı yaşam döngüsü
    def _connect(self):
        conn = self._factory(self.host, self.connect_timeout_s)
        conn.connect()
        if getattr(conn, "sock", None) is not None:
            conn.sock.settimeout(self.read_timeout_s)   # bağlandıktan sonra okuma bütçesi
        self.stats["connects"] += 1
        self._conn = conn
        self._last_use = self._clock()
        return conn

    def _get(self):
        idle = self._clock() - self._last_use
        if self._conn is not None and idle > self.max_idle_s:
            self.close()                                 # sunucu çoktan kapatmış olabilir
        if self._conn is None:
            return self._connect(), False
        self.stats["reused"] += 1
        return self._conn, True

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None

    # ---- istek
    def request(self, method: str, path: str, query: str = "", headers: dict | None = None) -> tuple[int, dict, bytes]:
        url = f"{path}?{query}" if query else path
        with self._lock:
            self.stats["requests"] += 1
            conn, reused = self._get()
            try:
                return self._send(conn, method, url, headers or {})
            except socket.timeout:
                self.stats["timeouts"] += 1
                self.close()
                raise
            except RETRYABLE:
                self.close()
                if method != "GET" or not reused:
                    self.stats["errors"] += 1
                    raise
                # Yeniden kullanılan bağlantı koptu: sunucu keep-alive'ı kapatmış. Okuma isteği
                # idempotent olduğu için bir kez, taze bağlantıyla tekrarlanır.
                self.stats["retries"] += 1
                return self._send(self._connect(), method, url, headers or {})
            except OSError:
                self.stats["errors"] += 1
                self.close()
                raise

    def _send(self, conn, method: str, url: str, headers: dict) -> tuple[int, dict, bytes]:
        conn.request(method, url, headers=headers)
        r = conn.getresponse()
        body = r.read()
        self._last_use = self._clock()
        if r.will_close:                                  # sunucu bağlantıyı kapattı
            self.close()
        return r.status, {k.lower(): v for k, v in r.getheaders()}, body

    def as_callable(self):
        """`TestnetClient.http` imzası: (method, path, query, headers, timeout)."""
        def call(method: str, path: str, query: str, headers: dict, timeout: float):
            return self.request(method, path, query, headers)
        return call
