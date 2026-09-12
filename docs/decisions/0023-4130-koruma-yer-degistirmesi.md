# ADR 0023 — `-4130`: koruma emri yer değiştirmesi miktar tabanlı olur

Tarih: 2026-09-12 · Durum: kabul edildi · **Planlı re-baseline #3**

Bu ADR `docs/design/faz4-cikis-kurallari.md`'deki "önce yeni SL, sonra eskisinin iptali" sırasının
**gerekçesini korur, aracını değiştirir**.

## Bağlam

Gate 0 testnet doğrulaması (`docs/binance-api-gate0-dogrulama.md` §7) şunu buldu: pozisyon açıkken
ikinci `STOP_MARKET closePosition=true` emri `-4130` ile reddediliyor.

R3 kâr kilidi kuralı `[PlaceAlgo(yeni SL), CancelAlgo(eski SL)]` üretiyor. Gerçek borsada olacak
olan şuydu:

1. Yeni SL → `-4130` ile reddedilir.
2. `CancelAlgo` bağımsız olarak işlenir ve **başarılı olur**.
3. Pozisyon **stop'suz** kalır; iç durum ise yeni stop'u koymuş sanır.

Yani kural, korumayı sıkılaştırmak yerine tamamen kaldırıyordu. `config/testnet.toml` içinde
`lock_trigger_pct = "0.30"` ile **açıktı**; bugün tetiklenmiyor çünkü `allowed_cells` boş.

## Ölçüm

`scripts/measure_4130.py`, gerçek testnet, üç koşu. Her koşu en küçük miktarla tek pozisyon açtı,
ölçüm biter bitmez kapattı; her koşu sonunda açık emir, algo ve pozisyon sayısı **sıfır**
doğrulandı (`docs/measure-4130.json`).

| Deney | Sonuç |
|---|---|
| İlk `STOP_MARKET closePosition=true` | KABUL |
| İkinci `STOP_MARKET closePosition=true` (eskisi dururken) | **RET `-4130`** |
| `TAKE_PROFIT_MARKET closePosition=true` (stop dururken) | **KABUL** |
| İki `STOP_MARKET closePosition=false` + miktar + `reduceOnly` yan yana | **KABUL** |
| `closePosition=true` stop dururken miktar tabanlı stop | **KABUL** |
| İptal → yeni sırası: korumasız pencere | **817 · 841 · 861 ms** |

İki düzeltme, Gate 0'ın okumasına göre:

- Kısıt **yön** başına değil, **tür** başına: aynı yönde bir `closePosition` stop ve bir
  `closePosition` take profit yan yana durabiliyor. Hata metni ("stop or take profit ... in the
  direction") bundan daha geniş görünüyor.
- Miktar tabanlı emir kısıtın **dışında**: hem kendi türüyle hem `closePosition` emriyle yan yana
  duruyor.

## Seçenekler

1. **Sırayı ters çevir** (iptal → yeni). Ölçülen korumasız pencere ~820–860 ms. Yeni emir de
   reddedilirse pencere bir sonraki tick'e kadar uzar.
2. **Yer değiştirmeyi miktar tabanlı yap** (`closePosition=false` + miktar + `reduceOnly`). Sıra
   korunur, korumasız pencere **yok**. Bedeli: miktar otomatik izlenmez.
3. **Yalnız uygulama tarafı yedek stop'a güven** (R1). Tek başına yetersiz: borsa tarafı koruma
   sistemin çökmesine karşı duran katmandır, uygulama katmanı onun yerine geçemez.

## Karar

**Seçenek 2.** İlk koruma `closePosition=true` kalır (miktarı otomatik izler, en güçlü garanti).
**Yer değiştirme** (R3) miktar tabanlı emirle yapılır; böylece "önce yeni, sonra iptal" sırası
korunur ve korumasız pencere oluşmaz. R1 uygulama tarafı yedek stop üçüncü katman olarak kalır.

Miktarın otomatik izlenmemesi kabul edilen bedeldir: kısmi çıkış (R4) pozisyonu küçültürse miktar
tabanlı stop fazla kalır, ama `reduceOnly=true` tetiklendiğinde borsa miktarı pozisyona kırpar.
Pozisyon **büyümez** (piramit yok, ADR 0004), yani ters yönde risk yoktur.

Adapter fail-closed: `closePosition=false` olup miktar verilmemişse emir gönderilmez.

## Re-baseline #3

`PlaceAlgo` komutuna `qty` alanı eklendi. `make golden-orders-diff`:

| alan | değişen komut | not |
|---|---|---|
| `PlaceAlgo.close_position` | 17 | yalnız yer değiştirme emirleri (`-SL-v2` ve sonrası) |
| `PlaceAlgo.qty` | 17 | aynı emirler; ilk korumada `None` kalır |

Komut sayısı (140) ve tür dağılımı değişmedi. Hash'in değişmesi 55 `PlaceAlgo`'nun tamamını kapsar
çünkü kanonik serileştirmeye yeni bir alan girdi; **anlamsal değişiklik 17 emirdedir**, kalan 38'de
alan `None`'dır.

`tests/golden/replay_baseline.json` değişmedi. Parite (Gate 5) korundu.

## Sonuçlar

- 707 → 714 test; `tests/test_protection_replace.py` bu yolu kilitliyor.
- Ölçüm betiği `scripts/measure_4130.py` olarak duruyor: mainnet davranışı **doğrulanmadı**,
  testnet sonucu mainnet için kanıt değildir (Gate 0 §1 ile aynı uyarı).
- Kısmi çıkış sonrası miktar tabanlı stop'un fazla kalması **ölçülmedi**; gerçek kısmi çıkış
  gerektirir.
