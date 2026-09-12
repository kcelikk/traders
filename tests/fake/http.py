"""Tek sahte HTTP istemcisi. Daha önce `test_testnet_client.py` ve `test_testnet_adapter.py`
içinde iki ayrı kopya vardı.

Enjeksiyon noktası üretim kodunda hazır: `TestnetClient.http` bir dataclass alanıdır
(`fbot/gateway/testnet.py`), yani bağımlılık enjeksiyonu için ek bir soyutlama gerekmez.
"""
from __future__ import annotations

import json

Response = tuple[int, dict, bytes]


def ok(payload, status: int = 200, headers: dict | None = None) -> Response:
    return status, headers or {}, json.dumps(payload).encode()


def err(status: int, code: int | None = None, msg: str = "hata", headers: dict | None = None) -> Response:
    body = {"msg": msg} if code is None else {"code": code, "msg": msg}
    return status, headers or {}, json.dumps(body).encode()


class FakeHTTP:
    """Sıradaki cevabı döndürür. Çağrılabilir öğeler `tests.fake.faults` enjeksiyonlarıdır.

    `calls` her isteği `(method, path, query, headers)` olarak kaydeder; testler hem çağrının
    yapıldığını hem de **yapılmadığını** doğrulayabilir.
    """

    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls: list[tuple] = []

    def __call__(self, method, path, query, headers, timeout):
        self.calls.append((method, path, query, dict(headers)))
        if not self.responses:
            raise AssertionError(f"beklenmeyen istek: {method} {path} (sırada cevap yok)")
        r = self.responses.pop(0)
        return r() if callable(r) else r

    @property
    def paths(self) -> list[str]:
        return [c[1] for c in self.calls]

    def queries_for(self, path: str) -> list[str]:
        return [c[2] for c in self.calls if c[1] == path]
