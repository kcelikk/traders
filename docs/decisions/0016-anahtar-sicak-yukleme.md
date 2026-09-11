# ADR 0016 — Testnet anahtarının çalışırken yüklenmesi

Tarih: 2026-09-11 · Durum: kabul edildi

## Bağlam

Testnet anahtarı konsoldan girilebiliyordu ama süreç anahtarı yalnızca açılışta, ortam
değişkeninden okuyordu. Konsol "servisin görmesi için yeniden başlatılması gerekir" uyarısı
veriyordu; kullanıcı her anahtar değişiminde komut satırına düşüyordu. Proje sahibi bunun
kaldırılmasını istedi: anahtar değişiminden sonra ek işlem olmamalı.

İkinci sorun: testnet ve mainnet anahtarları aynı `.env` dosyasındaydı. Dosya testnet
container'ına bağlansaydı, testnet süreci mainnet anahtarını da görürdü.

## Seçenekler

1. **Konsol container'ı yeniden başlatsın.** Docker soketini konsola vermek gerekir; konsol
   dışarıya açık olduğu için kabul edilemez.
2. **Süreç ortam değişkenini yeniden okusun.** Mümkün değil: ortam değişkeni süreç ömrü boyunca sabittir.
3. **Süreç anahtar dosyasını periyodik okusun.** Seçildi.

## Karar

`ArmingSupervisor` periyodik durum görevinde (10 s, sıcak yolun dışında) anahtar dosyasını
okur ve içerik parmak izi değiştiyse emir yolunu açar veya kapatır.

Kurallar:

- **Ayrı dosya.** Testnet anahtarı `data/state/testnet/credentials.env`; bu dizin zaten yalnızca
  testnet container'ına bağlı. Mainnet `.env`'de kalır ve hiçbir trading container'ına bağlanmaz.
- **Açık pozisyon varken uygulanmaz.** Koruma emirlerinin sahipliği el değiştirmesin diye
  değişiklik ertelenir, pozisyon kapanınca uygulanır.
- **Doğrulanmadan silahlanma yok.** Yeni anahtarla bakiye sorgusu başarısızsa servis silahsız kalır.
- **Fail-closed.** Bayrak ya da anahtar silinirse hemen silahsızlanır; dosya varsa ama okunamıyorsa
  (izin) yine silahsız kalır ve neden yazılır. Sessiz geri düşme yok.
- **Sızıntı yok.** Olaylara ve log'a yalnızca maskeli anahtar ve içerik parmak izi yazılır.
- **Dosya sahipliği.** Container kök olmayan kullanıcıyla koştuğu için konsol dosyayı 600 yazar ve
  sahibini servis kullanıcısına (uid 10001, `FBOT_SERVICE_UID` ile değiştirilebilir) verir.
  Veremezse yanıtta uyarı döner.

Mainnet için sıcak yükleme **yoktur**: `LiveExecutionAdapter` korumalı stub olduğu sürece
gereksizdir ve canlı emir yolunu web arayüzünden açmak kilitli kararlara aykırıdır.

## Sonuçlar

- Konsoldan anahtar değişimi komut satırı gerektirmez. Ölçüm: yazımdan 3 saniye sonra uygulandı,
  servis bakiyeyi doğrulayıp silahlandı.
- Konsol anahtar paneli servisin canlılık damgasından "silahlı / silahsız" durumunu gösterir,
  böylece değişikliğin ulaştığı görülür.
- Testnet container'ı mainnet anahtarını artık hiçbir koşulda göremez.
- Yeni sessiz başarısızlık yüzeyi: dosya izinleri. Buna karşı fail-closed davranış, yazımda
  sahiplik ataması ve `env_path_for` ile `testnet_paths` arasındaki bağı doğrulayan sözleşme testi eklendi.
