# Gate 4 ölçümü — sağlık modeli, reaktörler (shadow), devre kesici

Tarih: 2026-09-12 · Commit `2077502e7de0` · ADR 0021

## 1. Kapılar

| Kapı | Sonuç |
|---|---|
| `make test` | 627 → **661 geçti** |
| `make test-determinism` (saflık + iki process + iki golden) | yeşil |
| `tests/golden/replay_baseline.json` | **değişmedi** |
| `tests/golden/orders_baseline.json` | **değişmedi** |

## 2. Re-baseline #2 — beklenen fark **çıkmadı**, nedeni ölçüldü

Plan, sağlık modelinin (bayatlıkta çıkış kurallarının artık susmaması) golden'ı değiştirmesini
bekliyordu. `make golden-orders-diff` çıktısı:

```
hash_changed: false · commands 140 → 140 · changed_fields: {}
```

**Neden:** iki fixture'da da bayatlık penceresi **yok**. `rec-mini`'de strateji kapalı,
`tests/scenario.py` senaryosunda olaylar kesintisiz akıyor ve hiçbir kategori bayat olmuyor. Yani
davranış değişikliği gerçek, ama **pinlenmiş baseline'lar bu yolu hiç geçmiyor**.

Bu bir kapsam boşluğudur ve kayda geçirildi: davranış birim testleriyle korunuyor
(`tests/test_health.py`), golden ile değil. Bayatlık içeren bir fixture üretmek ayrı iştir.

## 3. Reactor bütçesi — `bookTicker` dalında +%20

Ölçüm `make bench-reactors`. Aynı fixture, **açık pozisyonlu** iki koşu (reactor kapalı / shadow).
Stop bilerek piyasanın üstünde seçildi: her olayda niyet üretilir, yani **en kötü durum** ölçülür.
Koşu başına 1.048 shadow niyet üretildiği doğrulandı; sıfır olsaydı ölçüm geçersiz sayılacaktı.

| koşu | kapalı p50 | shadow p50 | fark |
|---|---|---|---|
| 1 | 7,00 µs | 7,52 µs | **+7,4 %** |
| 2 | 6,97 µs | 8,66 µs | +24,2 % |
| 3 | 6,99 µs | 7,42 µs | +6,2 % |
| 4 | 7,03 µs | 7,70 µs | +9,5 % |
| 5 | 6,97 µs | 7,53 µs | +8,0 % |
| 6 | 7,13 µs | 8,00 µs | +12,2 % |

Medyan **+8,8 %**, bütçenin (+%20) altında. İkinci koşu aykırı: o koşuda toplam throughput da
68.330 → 57.198 olay/s düştü, yani makine gürültüsü. p99 değerleri koşudan koşuya 12–33 µs arasında
salınıyor; bu mikro-ölçümün kendi dağılımıdır, reaktörün etkisi p50'de okunmalıdır.

**Ölçülmedi:** reactor'ün gerçek faydası (çıkış kararı → emir gecikmesinde kazanç). Bunun için
gerçek pozisyon ve gerçek çıkış gerekir; shadow gözlemi bu veriyi toplayacak.

## 4. Canlı durum (dağıtımdan sonra)

```
breaker : mode alarm · day_net_usdt 0 · consecutive_losses 0 · tripped [] · entry_blocked null
exit_mode: FULL · shadow niyet: 0 · kill_switch: false
userdata : keys 1 · frames 0 · mode shadow
havuz    : 158 istek · 1 bağlantı · 0 timeout · 0 retry
```

Shadow niyet sayısı 0, çünkü açık pozisyon yok (`allowed_cells` boş). Reaktör açık pozisyon
olmadan O(1) dönüyor.

## BU ÖLÇÜMDE YAPILMAYANLAR

- **Reactor'ün shadow gözlemi yapılmadı.** Plan bir hafta gözlem ve "reactor'ün üreteceği çıkış ile
  gerçekte olanın karşılaştırması" istiyor; pozisyon açılmadığı için bugün veri yok.
- **Devre kesici hiç tetiklenmedi.** Kapanan işlem yok; yanlış-pozitif oranı ölçülemedi. `alarm`
  modunda kalması bu yüzden doğru.
- **`RunawayDetector` ve 418 yolu canlıda tetiklenmedi**; birim testleriyle doğrulandı.
- **Telemetri (4d) ve genişletilmiş re-baseline raporu (4e) yazılmadı.**
- `active` reactor modu **yok**: yapılandırmada seçilirse yükleme hata veriyor.
- Günlük zarar eşiği (40 USDT) **ölçülmüş bir değer değil**, 80 USDT × 5 pozisyon sınırının yarısı
  olarak seçildi; paper/testnet verisi biriktikçe güncellenecek.
