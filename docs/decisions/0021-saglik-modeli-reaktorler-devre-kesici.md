# ADR 0021 — Sağlık modeli, reaktörler ve devre kesici (Gate 4)

Tarih: 2026-09-12 · Durum: kabul edildi · Kapsam: Gate 4a–4c

Bu ADR `Engine._apply_freeze` davranışını (bayatlıkta topyekûn `FROZEN`) **supersede eder**.

## Bağlam

Üç yapısal boşluk:

1. **Bayatlık her şeyi susturuyordu.** Herhangi bir kategori bayatsa tüm açık pozisyonlar `FROZEN`
   oluyor, `_tick_positions` onları atlıyordu. Böylece **korumasız** bir pozisyonu kurtaracak kural
   (koruma zaman aşımı → acil çıkış) da susuyordu. Bayat fiyat "hiçbir şey yapma" demek değildir.
2. **Çıkış kuralları saniyede bir bakılıyordu.** Fiyat hareketi ile karar arasında 1 saniyeye kadar
   kuantizasyon var; kural `ctrl/tick` dışında hiç değerlendirilmiyordu.
3. **İki güvenlik yolu ölüydü.** `RunawayDetector` hiçbir yerde kurulmuyordu; `RateLimiter` 418'i
   işaretliyor ama kimse okumuyordu (`fbot/gateway/testnet.py` yalnız hata metnine ekliyordu).

## Karar

### 1. `fbot/core/health.py` — ortogonal gerçekler, türetilen izinler

Gerçekler ayrı ayrı ölçülür (`market_age`, `user_stream_age`, `reconciled`, `kill_switch`,
`warmup`), karar onlardan **türetilir**:

| `exit_mode` | ne zaman | hangi kurallar çalışır |
|---|---|---|
| `FULL` | veri taze | hepsi |
| `PROTECTION_ONLY` | market bayat | yalnız **borsa tarafı koruma eksikliğini** gideren kural (koruma zaman aşımı → acil çıkış) |
| `HALTED` | mutabakat yok | hiçbiri |

`HALTED` gerekçesi: iç durumun borsayla aynı olduğunu bilmiyorsak, hayalet bir pozisyona çıkış
emri göndermek gerçek bir pozisyonu ters çevirebilir. Her üç durumda da **borsa tarafı koruma
emri devrededir**; bu katman kaldırılmaz.

`PosState.FROZEN` artık **uygulanmıyor**. Enum değeri geriye dönük uyumluluk için duruyor.

### 2. `fbot/core/reactors.py` — olay-tetiklemeli değerlendirme, **shadow**

Registry + dispatcher. Determinizm garantileri: reaktör saat okumaz (`now_ns` parametre), registry
sabit sıralı, niyetler `(reactor_id, pos_id)` ile sıralanır, `exit_in_flight` (Gate 3) çift üretimi
engeller.

`CoreState.by_symbol` indeksi eklendi: olay başına tüm pozisyonları taramak kabul edilemez.
Açık pozisyon yoksa reaktör O(1) döner.

**Fiyat referansı kural başına deklare edilir.** İlk reaktör (R1 yedek stop) `MARK` kullanır, çünkü
borsadaki karşılığı `workingType=MARK_PRICE`; iki katmanın farklı fiyata bakması istenmez.

Shadow niyetler `ShadowIntent` komutu olarak **ayrı hash zincirine** yazılır; ana determinizm
testi etkilenmez. `mode="active"` **yoktur**: yapılandırmada seçilirse yükleme hata verir. Yarım
implementasyon bağlanmaz (CLAUDE.md); aktifleştirme shadow gözlemi + ayrı onay gerektirir.

**Coalescing/throttle yok**: önce ölçüldü. `bookTicker` dalında medyan +%8,8 (bütçe +%20),
`docs/gate4-olcum.md` §3.

### 3. `fbot/core/breaker.py` — devre kesici, `alarm` ile başlar

Üç şey ayrı tutulur: arıza dedektörü (yazılım hatası), günlük net zarar (piyasa sonucu), kalıcı
kill switch (son katman).

Günlük net zarar ve ardışık zarar limiti aşımında **yeni giriş durur**; açık pozisyonlar mevcut
politikayla yönetilmeye devam eder — panik satışı politikası değildir. Gün sınırı **borsa zaman
damgasından** hesaplanır, iç saatten değil (Rule Zero #2).

`mode = "alarm"` varsayılandır: karar değişmez, yalnız olay üretilir. `enforce`'a geçiş yanlış-
pozitif sayımından sonra yapılır. Eşik (40 USDT) **ölçülmüş bir değer değildir**; 80 USDT × 5
pozisyon sınırının yarısı olarak seçildi ve veri biriktikçe güncellenecek.

`RunawayDetector` artık kuruluyor ve tetiklendiğinde kalıcı kill switch'i çalıştırıyor; 418 ban da
aynı yere bağlandı.

## Sonuçlar

- İki golden de değişmedi. **Beklenen re-baseline #2 farkı çıkmadı**: fixture'larda bayatlık
  penceresi yok, yani pinlenmiş baseline'lar bu yolu hiç geçmiyor. Kapsam boşluğu kayıtlı
  (`docs/gate4-olcum.md` §2); davranış birim testleriyle korunuyor.
- 627 → 661 test.
- **Açık:** reactor shadow gözlemi (pozisyon açılmadığı için veri yok), devre kesicinin yanlış-
  pozitif oranı, telemetri (4d) ve genişletilmiş re-baseline raporu (4e).
