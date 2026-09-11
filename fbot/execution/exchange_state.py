"""Borsa durumunun çekilmesi: mutabakatın girdisi. I/O kenarı.

CLAUDE.md mutlak kuralı: *"Açılışta mutabakat: borsa tek doğruluk kaynağıdır. Açık pozisyon ve
emirler borsadan çekilir, iç state ile karşılaştırılır, uyuşmazlıkta trading kilitlenir."*

Doğrulanmış uçlar (testnet üzerinde 2026-09-11'de çağrılarak teyit edildi):
  · `GET /fapi/v2/positionRisk` → `symbol`, `positionAmt` (işaretli), `leverage`, `positionSide`
  · `GET /fapi/v1/openOrders` → `symbol`, `clientOrderId`
  · `GET /fapi/v1/openAlgoOrders` → `symbol`, `clientAlgoId`, `algoStatus`
  · `GET /fapi/v1/positionSide/dual` → `{"dualSidePosition": bool}`

**Fail-closed:** herhangi bir çağrı başarısız olursa boş snapshot dönmek yerine `SnapshotError`
atılır. Boş snapshot "borsada hiçbir şey yok" demektir; hata bunu söyleyemez.

Yalnızca yapılandırılmış sembol evreni dikkate alınır: hesapta başka semboller olabilir, onlar
bizim sorumluluğumuzda değildir.

**Her istek kendi zaman damgasını alır.** Dört imzalı isteğe tek damga paylaştırıldığında
sonuncular `recvWindow`'u aşıp `-1021` ile reddediliyordu; `positionRisk` 740 satır döndüğü için
toplam süre 5 saniyeyi geçebiliyor.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from fbot.core.reconcile import ExchangeSnapshot, reconcile


class SnapshotError(RuntimeError):
    """Borsa durumu okunamadı. Mutabakat yapılamaz → trading kilitli kalır."""


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v))
    except (InvalidOperation, TypeError, ValueError):
        raise SnapshotError(f"sayıya çevrilemeyen alan: {v!r}") from None


def fetch_snapshot(client, symbols: set[str], now_ms) -> ExchangeSnapshot:
    """`now_ms` bir sayı ya da her çağrıda taze damga veren bir fonksiyon olabilir."""
    tick = now_ms if callable(now_ms) else (lambda: now_ms)
    try:
        mode = client.signed("GET", "/fapi/v1/positionSide/dual", {}, tick())
        rows = client.positions(tick())
        orders = client.open_orders(tick())
        algos = client.open_algos(tick())
    except SnapshotError:
        raise
    except Exception as e:  # noqa: BLE001 — her hata mutabakatsızlık demektir
        raise SnapshotError(f"borsa durumu okunamadı: {e}") from e

    positions, leverage = {}, {}
    for r in rows or []:
        sym = r.get("symbol")
        if sym not in symbols:
            continue
        amt = _dec(r.get("positionAmt", 0))
        if r.get("leverage") is not None:
            leverage[sym] = int(_dec(r["leverage"]))
        if amt == 0:
            continue
        positions[sym] = {"side": "long" if amt > 0 else "short", "qty": abs(amt)}

    open_orders: dict[str, set] = {}
    for o in orders or []:
        if o.get("symbol") in symbols and o.get("clientOrderId"):
            open_orders.setdefault(o["symbol"], set()).add(o["clientOrderId"])

    open_algos: dict[str, set] = {}
    for a in algos or []:
        if a.get("symbol") in symbols and a.get("clientAlgoId") and a.get("algoStatus") == "NEW":
            open_algos.setdefault(a["symbol"], set()).add(a["clientAlgoId"])

    dual = (mode or {}).get("dualSidePosition")
    return ExchangeSnapshot(positions=positions, open_algos=open_algos, open_orders=open_orders,
                            leverage=leverage, position_mode="HEDGE" if dual else "ONE_WAY")


def internal_view(positions: dict) -> dict:
    """Çekirdek pozisyonlarını mutabakatın beklediği biçime çevirir. Kapanmışlar dışarıda kalır."""
    out = {}
    for pid, p in positions.items():
        if getattr(p.state, "value", p.state) == "CLOSED":
            continue
        out[pid] = {"symbol": p.symbol, "side": p.side, "qty": p.qty, "algos": set(p.active_algos)}
    return {"positions": out}


class ReconcileSupervisor:
    """Açılışta ve periyodik olarak mutabakat yapar; sonucu tek bir olayda bildirir.

    Kilitleme fail-closed: borsa okunamazsa, istemci yoksa ya da fark varsa `reconciled=False`.
    Aynı sonuç tekrar tekrar olay üretmez; yalnızca durum değişince bildirilir.
    """

    def __init__(self, client, symbols: set[str], positions, expected_leverage: dict):
        self.client = client
        self.symbols = set(symbols)
        self.positions = positions              # () -> {pos_id: Position}
        self.expected_leverage = dict(expected_leverage)
        self.last: tuple | None = None

    def check(self, now_ms) -> dict | None:
        ev = self._evaluate(now_ms)
        key = (ev["reconciled"], tuple(ev["mismatches"]), tuple(ev["unprotected"]), ev["reason"])
        if key == self.last:
            return None
        self.last = key
        return ev

    def _evaluate(self, now_ms) -> dict:
        if self.client is None:
            return {"kind": "reconcile", "reconciled": False, "mismatches": [], "unprotected": [],
                    "reason": "borsa istemcisi yok (silahsız): mutabakat yapılamadı"}
        try:
            snap = fetch_snapshot(self.client, self.symbols, now_ms)
        except SnapshotError as e:
            return {"kind": "reconcile", "reconciled": False, "mismatches": [], "unprotected": [],
                    "reason": str(e)}
        r = reconcile(internal_view(self.positions()), snap, self.expected_leverage)
        ok = r.ok and not r.unprotected
        return {"kind": "reconcile", "reconciled": ok, "mismatches": r.mismatches,
                "unprotected": r.unprotected,
                "reason": "tamam" if ok else ("korumasız pozisyon: " + ", ".join(r.unprotected)
                                              if r.unprotected and not r.mismatches
                                              else "; ".join(r.mismatches[:6]))}
