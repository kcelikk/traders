"""Emir kaydı (OMS): `clientOrderId` → pozisyon, rol ve durum. **Saf**, çekirdeğin parçası.

Neden burada ve `map_user_event`'te değil: user data çerçevesi `pos_id` taşımaz, yalnız
`clientOrderId` taşır. Eşleme I/O kenarında yapılırsa replay'de yeniden kurulamaz ve determinizm
kırılır. Kayıt çekirdek durumunun parçasıdır: aynı olay dizisi aynı kaydı üretir.

İki iş yapar:

1. **Kimlik çözümü.** `cid → pos_id, rol`. Gramerden de çıkarılabilir (`fbot/core/ids.py`) ama
   kayıt asıl kaynaktır: gramer değişirse eski emirler yine çözülür.
2. **Mantıksal niyet defteri.** Aynı mantıksal niyet (örn. "p1 pozisyonunu kapat") için ikinci bir
   emir üretilmesini engeller. Gate 0 §5 gösterdi ki borsa aynı `clientOrderId` ile ikinci emri
   **reddetmiyor**, ikisi de doluyor; yani dedupe borsanın reddine dayanamaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from fbot.core.ids import pos_id_of

ENTRY, EXIT, PROTECTIVE, PARTIAL = "entry", "exit", "protective", "partial"
ROLES = (ENTRY, EXIT, PROTECTIVE, PARTIAL)

PENDING, ACKED, PART, FILLED, DONE, UNKNOWN = "PENDING", "ACKED", "PARTIALLY_FILLED", "FILLED", "DONE", "UNKNOWN"
TERMINAL = (FILLED, DONE)
# Durum geriye düşmez: sıra dışı gelen eski olay terminal durumu bozamaz.
_RANK = {PENDING: 0, ACKED: 1, PART: 2, UNKNOWN: 2, FILLED: 3, DONE: 3}

_STATUS_STATE = {"NEW": ACKED, "PARTIALLY_FILLED": PART, "FILLED": FILLED,
                 "CANCELED": DONE, "EXPIRED": DONE, "EXPIRED_IN_MATCH": DONE, "REJECTED": DONE}


@dataclass
class OrderRef:
    client_id: str
    pos_id: str
    role: str
    symbol: str
    submitted_ns: int
    state: str = PENDING
    order_id: int | None = None
    intent_key: str | None = None
    strategy_id: str | None = None

    @property
    def is_terminal(self) -> bool:
        return self.state in TERMINAL


@dataclass
class OrderRegistry:
    refs: dict = field(default_factory=dict)          # cid → OrderRef
    by_intent: dict = field(default_factory=dict)     # mantıksal niyet → cid
    unknown: set = field(default_factory=set)         # yürütme durumu bilinmeyen cid'ler

    # ---- kayıt
    def register(self, client_id: str, pos_id: str, role: str, symbol: str, now_ns: int,
                 intent_key: str | None = None, strategy_id: str | None = None) -> OrderRef:
        if role not in ROLES:
            raise ValueError(f"bilinmeyen rol: {role!r}")
        ref = self.refs.get(client_id)
        if ref is not None:
            return ref                                 # aynı cid iki kez kaydedilmez
        ref = OrderRef(client_id=client_id, pos_id=pos_id, role=role, symbol=symbol,
                       submitted_ns=now_ns, intent_key=intent_key, strategy_id=strategy_id)
        self.refs[client_id] = ref
        if intent_key is not None:
            self.by_intent[intent_key] = client_id
        return ref

    # ---- çözüm
    def get(self, client_id: str) -> OrderRef | None:
        return self.refs.get(client_id)

    def resolve_pos(self, client_id: str) -> str | None:
        """Kayıt önce, gramer sonra. Kayıtta yoksa gramer bir tahmindir; bilinmiyorsa `None`."""
        ref = self.refs.get(client_id)
        if ref is not None:
            return ref.pos_id
        guess = pos_id_of(str(client_id))
        return guess if guess and guess != client_id else None

    def role_of(self, client_id: str) -> str | None:
        ref = self.refs.get(client_id)
        return ref.role if ref else None

    # ---- niyet defteri (dedupe)
    def intent_open(self, intent_key: str) -> bool:
        """Bu mantıksal niyet için hâlâ terminal olmayan bir emir var mı?"""
        cid = self.by_intent.get(intent_key)
        if cid is None:
            return False
        ref = self.refs.get(cid)
        return ref is not None and not ref.is_terminal

    # ---- durum geçişleri
    def on_event(self, ev: dict) -> OrderRef | None:
        """`map_user_event` çıktısını uygular. Bilinmeyen cid kaydedilmez: yabancı emir bizim değil."""
        cid = ev.get("client_id") or ev.get("client_algo_id")
        ref = self.refs.get(cid)
        if ref is None:
            return None
        if ev.get("order_id") is not None:
            ref.order_id = ev["order_id"]
        state = _STATUS_STATE.get(ev.get("status") or "")
        if state is None:
            kind = ev.get("kind", "")
            state = {"order_fill": PART, "algo_ack": ACKED, "algo_triggered": PART,
                     "algo_canceled": DONE, "algo_rejected": DONE, "algo_finished": DONE}.get(kind)
        if state is not None and _RANK[state] >= _RANK[ref.state]:
            ref.state = state
        if ref.state in TERMINAL:
            self.unknown.discard(cid)
        return ref

    def mark_unknown(self, client_id: str) -> OrderRef | None:
        """Yürütme durumu bilinmiyor (timeout / 503 / -2022). Terminal emir geri alınmaz."""
        ref = self.refs.get(client_id)
        if ref is None or ref.is_terminal:
            return ref
        ref.state = UNKNOWN
        self.unknown.add(client_id)
        return ref

    # ---- bakım
    def sweep(self, now_ns: int, ttl_ns: int) -> list:
        """Cevapsız kalan emirler `UNKNOWN`a düşer: sessizce `PENDING` kalmak, mutabakatın
        çözmesi gereken bir durumu görünmez kılar."""
        out = []
        for cid in sorted(self.refs):
            ref = self.refs[cid]
            if ref.state == PENDING and now_ns - ref.submitted_ns >= ttl_ns:
                self.mark_unknown(cid)
                out.append(cid)
        return out

    def open_by_pos(self, pos_id: str, role: str | None = None) -> list:
        return [self.refs[c] for c in sorted(self.refs)
                if self.refs[c].pos_id == pos_id and not self.refs[c].is_terminal
                and (role is None or self.refs[c].role == role)]
