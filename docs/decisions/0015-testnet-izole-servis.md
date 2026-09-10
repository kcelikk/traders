# ADR 0015 — Testnet: izole servis, REST + HMAC emir yolu

Tarih: 2026-09-10 · Durum: kabul edildi (proje sahibi: "testnet için 9 ve 10 onay")

## Bağlam
Proje sahibi testnet'i ayrı ve izole bir ortam olarak istedi: canlıda bir strateji çalışırken paper ve testnet'te başka stratejiler denenebilmeli. CLAUDE.md iki kapı koyuyordu: canlı emir gönderen kod yolunu aktif etmek ve yeni bağımlılık. İkisi de onaylandı (9 ve 10).

## Kararlar

1. **Emir yolu: REST + HMAC SHA256 (stdlib).** Kilitli karar "WebSocket API + Ed25519" idi; testnet HMAC anahtarı verdiği ve WS API `session.logon` yalnızca Ed25519 kabul ettiği için testnet'te REST kullanılır. **Yeni bağımlılık yok** (`hmac`, `hashlib`, `urllib` stdlib). Ed25519 ve WS API yolu Faz 10 öncesinde ayrı ADR ile değerlendirilir.
2. **Uç noktalar sabit ve yalnızca testnet.** `https://testnet.binancefuture.com` kodda sabittir; mainnet URL'si testnet modülünde **hiç bulunmaz**, config'den de verilemez. Yanlış ortama emir gönderme yolu yoktur.
3. **Üç kapılı silahlanma.** Emir gönderilebilmesi için hepsi gerekir: `FBOT_TESTNET_ARMED` ortam değişkeni, `.env` içinde anahtar çifti, config'de `mode = "testnet"`. Biri eksikse süreç emir göndermez ve nedenini yazar.
4. **İzolasyon.** Kendi container'ı (`fbot-testnet`), kendi kayıt dizini, kendi WS bağlantıları, kendi SQLite'ı, kendi kill switch dosyası (`data/state/testnet/`). Paper ve recorder'dan tamamen ayrı. Ortak olan tek şey ana makine.
5. **Güvenlik.** Anahtarlar yalnızca ortam değişkeninden; `Credentials.__repr__` maskeli; anahtar hiçbir log, kayıt ya da image'a yazılmaz. `.env` gitignore'da. Testnet anahtarında çekim yetkisi zaten yoktur, yine de IP whitelist önerilir.
6. **Rate limit ve emir durumu gerçek sayaçlarla.** `fbot/core/rate_limit.py` (iki bucket, header ve WS `rateLimits` senkronu, 429 geri çekilme, 418 kill switch) ve `fbot/core/order_state.py` (tradeId ile tekrar bastırma, kısmi dolum birikimi, `EXPIRED_IN_MATCH`) testnet'ten önce yazıldı ve testlendi.

## Kapsam dışı (bu ADR'de yapılmayan)
- Canlı (mainnet) emir yolu: ayrı ADR ve ayrı onay ister.
- WS API + Ed25519: Faz 10 öncesi.
- Testnet sonuçlarının kârlılık kanıtı sayılması: testnet defteri incedir, fiyatlar mainnet'ten sapar; testnet **tesisat doğrulama** ortamıdır (emir yaşam döngüsü, hata kodları, rate limit, koruma emirlerinin gerçekten yerleşmesi).

## Sonuçlar
- `fbot/gateway/signing.py`, `fbot/gateway/testnet.py`, `fbot/testnet/main.py`, `config/testnet.toml`, compose servisi `testnet`.
- Faz 9 test planındaki 10 madde bu servisle koşulur; sonuçlar `docs/testnet-dogrulama.md` dosyasına yazılır.
