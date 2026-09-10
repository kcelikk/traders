# ADR 0003 — User data stream mekanizması: kilitli karar dokümanla çelişiyor

Tarih: 2026-09-10 · Durum: **KABUL EDİLDİ** (proje sahibi, 2026-09-10) — seçenek A

## Bağlam

Kilitli karar: "`session.logon` + `userDataStream.subscribe`. listenKey keepalive döngüsü yazma."

Doğrulama (bkz. `docs/binance-api-verification.md` §2), 2026-09-10 itibarıyla USDⓈ-M Futures dokümanında:

- `session.logon` **var** (ws-fapi, yalnızca Ed25519). Emir gönderme yolu için kullanılabilir.
- `userDataStream.subscribe` **yok**. Bu metot yalnızca Spot WebSocket API dokümanında bulunuyor.
- Futures WS API'de user data metotları: `userDataStream.start`, `userDataStream.ping`, `userDataStream.stop`. Hepsi listenKey döndürür. "The stream will close after 60 minutes unless a keepalive is sent."
- Private stream bağlantısı listenKey ile kurulur: `wss://fstream.binance.com/private/ws?listenKey=<listenKey>&events=ORDER_TRADE_UPDATE/ACCOUNT_UPDATE`.
- Futures changelog'unda listenKey deprecation girişi yok.

Yani Futures'ta user data akışı bugün listenKey'siz alınamıyor; keepalive yapılmazsa akış 60 dakikada kapanır.

## Seçenekler

**A. listenKey + keepalive, minimum yüzeyle.**
`userDataStream.start` (WS API üzerinden, aynı ws-fapi bağlantısında) → listenKey → `/private/ws?listenKey=…&events=…` bağlantısı. Her 30 dakikada `userDataStream.ping`. `listenKeyExpired` event'i ve bağlantı kopması aynı yeniden bağlanma yolunu tetikler; yeniden bağlanma sonrası REST ile pozisyon/emir mutabakatı zorunlu.
- Artı: dokümanla birebir uyumlu, tek yol.
- Eksi: kilitli kararı değiştirir. Keepalive kaçarsa 60 dk sonra sessiz kopuş → bayatlık izleyicisi bunu yakalamak zorunda (zaten var).

**B. Kilitli kararı koru, Binance Futures'a `subscribe` gelene kadar bekle.**
- Eksi: tarih yok. Faz 9 bloke olur.

**C. Spot'taki `userDataStream.subscribe` semantiğini Futures'ta dene.**
- Eksi: dokümansız davranışa dayanmak "uydurma yok" kuralını ihlal eder. Reddedildi.

## Öneri

**A.** Kararın özü olan "listenKey döngüsü yazma" ifadesinin amacı, gereksiz karmaşıklık ve sessiz kopuş riskinden kaçınmaktı. Bu risk keepalive'ı ayrı bir "döngü" olarak değil, private bağlantı yaşam döngüsünün bir parçası olarak ele alıp bayatlık izleyicisi + `listenKeyExpired` + yeniden bağlanma sonrası mutabakat ile yönetilir.

Emir gönderme yolu değişmez: ws-fapi + Ed25519 + `session.logon`.

## Sonuçlar (A kabul edilirse)

- CLAUDE.md "Kimlik doğrulama" satırı güncellenir: "session.logon (emir yolu) + listenKey tabanlı private stream; keepalive private bağlantı yöneticisinin parçası, 30 dk."
- Faz 1 gateway tasarımında private bağlantı için: listenKey alma, 30 dk ping, `listenKeyExpired` yakalama, yeniden bağlanma + mutabakat.
- Faz 9'da testnet'te 60 dk sınırı ve `listenKeyExpired` davranışı ölçülür.
- Bu ADR'yi ilk ADR olarak numaralandırmıyorum; 0001 build-vs-buy için ayrıldı.
