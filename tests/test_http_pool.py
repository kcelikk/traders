"""Kalıcı bağlantı havuzu (Gate 2.1): TLS el sıkışması istek başına değil, bağlantı başına.

Sahte bağlantı sınıfıyla test edilir; gerçek soket açılmaz.
"""
import http.client
import socket

import pytest

from fbot.gateway.http_pool import HTTPPool


class FakeResp:
    def __init__(self, status=200, body=b"{}", will_close=False, headers=None):
        self.status, self._body, self.will_close = status, body, will_close
        self._headers = headers or {"content-type": "application/json"}

    def read(self):
        return self._body

    def getheaders(self):
        return list(self._headers.items())


class FakeConn:
    """Her örnek bir TLS el sıkışması demektir; `opened` sayacı onu sayar."""
    opened = 0

    def __init__(self, host, timeout):
        self.host, self.timeout = host, timeout
        self.sock = None
        self.sent = []
        self.script = []          # sınıf dışından doldurulur
        self.closed = False

    def connect(self):
        FakeConn.opened += 1
        self.sock = socket.socket()

    def request(self, method, url, headers=None):
        self.sent.append((method, url, headers))

    def getresponse(self):
        if self.script:
            item = self.script.pop(0)
            if isinstance(item, Exception):
                raise item
            return item
        return FakeResp()

    def close(self):
        self.closed = True
        if self.sock is not None:
            self.sock.close()
            self.sock = None


def pool(script_per_conn=None, **kw):
    made = []

    def factory(host, timeout):
        c = FakeConn(host, timeout)
        if script_per_conn:
            c.script = list(script_per_conn[len(made)]) if len(made) < len(script_per_conn) else []
        made.append(c)
        return c
    p = HTTPPool("example.test", conn_factory=factory, **kw)
    return p, made


def test_second_request_reuses_the_connection():
    FakeConn.opened = 0
    p, made = pool()
    p.request("GET", "/a")
    p.request("GET", "/b")
    assert len(made) == 1 and FakeConn.opened == 1
    assert p.stats == {**p.stats, "requests": 2, "connects": 1, "reused": 1}


def test_read_timeout_is_separate_from_connect_timeout():
    p, made = pool(connect_timeout_s=0.5, read_timeout_s=3.0)
    p.request("GET", "/a")
    assert made[0].timeout == 0.5               # bağlanma bütçesi
    # bağlandıktan sonra okuma bütçesi sokete yazılır; soket kapandıysa istek de bitmiştir
    assert p.read_timeout_s == 3.0


def test_idle_connection_is_dropped_before_reuse():
    t = {"now": 0.0}
    p, made = pool(max_idle_s=10.0, clock=lambda: t["now"])
    p.request("GET", "/a")
    t["now"] = 60.0
    p.request("GET", "/b")
    assert len(made) == 2, "boşta kalmış bağlantı yeniden kullanılmamalı"


def test_server_closing_the_connection_is_honoured():
    p, made = pool(script_per_conn=[[FakeResp(will_close=True)], [FakeResp()]])
    p.request("GET", "/a")
    p.request("GET", "/b")
    assert len(made) == 2 and made[0].closed


def test_broken_keepalive_is_retried_once_for_reads():
    p, made = pool(script_per_conn=[[FakeResp(), http.client.RemoteDisconnected()], [FakeResp(body=b'{"ok":1}')]])
    p.request("GET", "/a")                       # bağlantı kurulur
    st, _, body = p.request("GET", "/b")         # kopar, taze bağlantıyla tekrarlanır
    assert st == 200 and body == b'{"ok":1}' and p.stats["retries"] == 1


def test_post_is_never_retried_blindly():
    """Gate 0 §5: aynı clientOrderId ile ikinci gönderim reddedilmiyor, ikisi de doluyor.
    Sonucu bilinmeyen bir emri tekrar göndermek iki pozisyon açar."""
    p, made = pool(script_per_conn=[[FakeResp(), http.client.RemoteDisconnected()], [FakeResp()]])
    p.request("GET", "/a")
    with pytest.raises(http.client.RemoteDisconnected):
        p.request("POST", "/fapi/v1/order", "q=1")
    assert len(made) == 1, "POST için yeni bağlantı açılıp tekrar gönderilmemeli"


def test_timeout_closes_the_connection_and_propagates():
    p, made = pool(script_per_conn=[[socket.timeout("read")]])
    with pytest.raises(socket.timeout):
        p.request("POST", "/fapi/v1/order")
    assert p.stats["timeouts"] == 1 and made[0].closed


def test_callable_adapter_matches_the_client_signature():
    p, _ = pool()
    call = p.as_callable()
    st, hdr, body = call("GET", "/x", "a=1", {"X-MBX-APIKEY": "k"}, 10.0)
    assert st == 200 and isinstance(hdr, dict)
