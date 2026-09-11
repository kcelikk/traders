"""Silahlanma denetçisi: anahtar dosyası değişince testnet emir yolunu çalışırken açar/kapatır.

Neden: anahtar konsoldan girildiğinde servisin yeniden başlatılması gerekiyordu. Emir yolunu
açıp kapatan bir bileşen olduğu için kurallar sıkı tutuldu:

  · Değişiklik **açık pozisyon yokken** uygulanır. Pozisyon açıkken erteleme olayı üretilir,
    koruma emirlerinin sahipliği el değiştirmez.
  · Borsa erişimi doğrulanmadan silahlanılmaz: yeni anahtarla bakiye sorgusu başarısızsa servis
    silahsız kalır.
  · Bayrak ya da anahtar silinirse **hemen** silahsızlanır, doğrulama beklenmez.
  · Olaylara gizli anahtar yazılmaz; yalnızca maskeli anahtar ve içerik parmak izi.

Sıcak yolda değildir: çağrı periyodik durum görevinden gelir (ADR 0015 · Faz 9).
"""
from __future__ import annotations

from pathlib import Path

from fbot.gateway.credfile import read_testnet_state


class ArmingSupervisor:
    def __init__(self, env_path, make_client, probe, adapter, open_positions, environ: dict | None = None):
        # tek dosya ya da dosya listesi; listede sonraki değer öncekini ezer
        self.env_path = [Path(env_path)] if isinstance(env_path, (str, Path)) else [Path(x) for x in env_path]
        self.make_client = make_client          # Credentials -> istemci
        self.probe = probe                      # istemci -> USDT bakiyesi (borsa erişimi kanıtı)
        self.adapter = adapter                  # rearm(client, armed)
        self.open_positions = open_positions    # () -> açık pozisyon sayısı
        self.environ = environ
        self.applied: str | None = None         # uygulanan son parmak izi
        self.deferred: str | None = None        # ertelenen parmak izi (tekrar tekrar olay üretmemek için)

    def check(self) -> dict | None:
        st = read_testnet_state(self.env_path, self.environ)
        if st.fingerprint == self.applied:
            return None
        if self.open_positions():
            # Pozisyon açıkken emir yolunun kimliği değiştirilmez; kapanınca uygulanır
            if st.fingerprint == self.deferred:
                return None
            self.deferred = st.fingerprint
            return {"kind": "arming_deferred", "armed": self.adapter.armed, "fingerprint": st.fingerprint,
                    "masked": st.masked, "reason": "açık pozisyon var, değişiklik pozisyon kapanınca uygulanacak"}
        self.deferred = None
        if not st.armed:
            self.adapter.rearm(None, False)
            self.applied = st.fingerprint
            return {"kind": "arming_changed", "armed": False, "fingerprint": st.fingerprint,
                    "masked": st.masked, "reason": st.reason}
        client = self.make_client(st.creds)
        try:
            balance = self.probe(client)
        except Exception as e:  # noqa: BLE001 — her hata silahsız kalmakla sonuçlanır (fail-closed)
            self.adapter.rearm(None, False)
            self.applied = st.fingerprint
            return {"kind": "arming_changed", "armed": False, "fingerprint": st.fingerprint, "masked": st.masked,
                    "reason": f"borsa erişimi doğrulanamadı: {e}"}
        self.adapter.rearm(client, True)
        self.applied = st.fingerprint
        return {"kind": "arming_changed", "armed": True, "fingerprint": st.fingerprint, "masked": st.masked,
                "reason": st.reason, "balance_usdt": balance}
