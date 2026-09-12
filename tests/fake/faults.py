"""Hata enjeksiyonu: bir cevabın yerine geçen çağrılabilir nesneler.

`FakeHTTP` sırasındaki bir öğe çağrılabilirse çağrılır; böylece cevap yerine istisna fırlatılabilir
ya da gecikme eklenebilir. Bugüne kadar repoda **timeout ve bağlantı kopması hiç enjekte
edilmiyordu**; bu modül o boşluğu kapatır.
"""
from __future__ import annotations

import socket
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Fault:
    """Çağrıldığında istisna fırlatan ya da gecikme ekleyip cevap dönen enjeksiyon."""
    exc: BaseException | None = None
    delay_s: float = 0.0
    response: tuple | None = None

    def __call__(self):
        if self.delay_s:
            time.sleep(self.delay_s)
        if self.exc is not None:
            raise self.exc
        return self.response


def timeout() -> Fault:
    """Okuma zaman aşımı. `socket.timeout` Python 3.10+ içinde `TimeoutError`'ın takma adıdır."""
    return Fault(exc=socket.timeout("timed out"))


def drop_connection() -> Fault:
    return Fault(exc=ConnectionResetError("connection reset by peer"))


def delay(seconds: float, response: tuple) -> Fault:
    """Cevap doğru ama geç gelir: event loop'un bloklanıp bloklanmadığını ölçmek için."""
    return Fault(delay_s=seconds, response=response)


def malformed(status: int = 200) -> Fault:
    """JSON olmayan gövde."""
    return Fault(response=(status, {}, b"<html>bozuk</html>"))
