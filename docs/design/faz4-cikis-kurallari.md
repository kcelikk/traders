# Faz 4 tasarım notu — pozisyon yönetimi ve çıkış kuralları

Tarih: 2026-09-10 · Durum: tasarım notu, kod yok. Faz 4 ancak Faz 3 DUR kapısı geçilirse başlar; geçilmezse bu not arşivdir.

## 1. Amaç

Açık pozisyonu **kârda kapatmak** birincil hedeftir (CLAUDE.md). Çıkış mantığı girişten önce tasarlanır ve önce test edilir. Kârdaki pozisyonun zarara dönmesi, kaçırılan girişten pahalıdır; tasarımın merkezi budur.

## 2. Dayanaklar (ölçülmüş / doğrulanmış)

| Konu | Değer | Kaynak |
|---|---|---|
| Tepki döngüsü (veri → karar → emir ACK) | p50 ≈ 0.42 s, p99 ≈ 1 s, seyrek 7 s tepe | `docs/latency-baseline.md` |
| Gidiş-dönüş maliyet (taker/taker) | ≈ %0.10 notional; maker/taker %0.07 | `docs/unit-economics.md` |
| İşlem büyüklüğü | 80 USDT notional; BTC/ETH 10x, diğerleri 5x | ADR 0004 |
| Koşullu emirler | `POST /fapi/v1/algoOrder` / WS `algoOrder.place`, `algoType=CONDITIONAL`, `triggerPrice`, `clientAlgoId`, `closePosition=true` ile `quantity`/`reduceOnly` yasak; **algo emirde modify yok** → cancel + place; bildirim `ALGO_UPDATE`; hesap başına 200 koşullu emir | `docs/binance-api-verification.md` §3 |
| Uygulama çıkışları | `reduceOnly=true`; STP modu seçilebilir, `EXPIRED_IN_MATCH` durumu | §3 |
| LIMIT modify | yalnızca LIMIT; kuyruk önceliği kaybı | §3 |
| 503 "Unknown error" | yürütme durumu **bilinmiyor**, başarısız sayılmaz | §4 |
| Volatil piyasada REST gecikir | pozisyon/emir gerçeği user data stream'den | §2 |
| Sinyal ufku | ≥ 10 s; araştırma ufukları 1/5/15/60 dk | Faz 0, ADR 0008 |

Sonuç: 1 saniyede %0.1'den hızlı hareketlerde uygulama tarafı çıkış yetişmez; **borsa tarafı koruma tek güvenilir güvenlik ağıdır**. Uygulama tarafı çıkış, yavaş bozulma ve kâr koruma içindir.

## 3. Fiyat referansları (kilitli ayrım)

| Referans | Faz 4 önerisi | Gerekçe |
|---|---|---|
| `trigger_price_source` (borsa SL/TP) | `workingType = MARK_PRICE`, `priceProtect = true` | Tek işlemlik fitil tetiklemesini azaltır; mark fiyatı likidasyon referansıyla aynı. **Config'den, sembol başına**; ölçüm (Faz 7) sonrası kesinleşir. |
| `pnl_accounting_source` | mark fiyatı (gerçekleşmemiş), Binance income (gerçekleşmiş) | Borsa ile mutabakat aynı kaynaktan |
| `execution_price_estimate` | bookTicker karşı taraf (long çıkış → best bid) − defter yürüyüşü | 80 USDT'de slippage ≈ 0 ölçüldü; yine de defterden |

Uygulama tarafı kurallar bu üçünü ayrı ayrı okur; tek "fiyat" kavramı yok.

## 4. Pozisyon yaşam döngüsü (durum makinesi, saf çekirdekte)

```
ENTRY_SENT ──fill──▶ PROTECTING ──SL+TP ACK──▶ MANAGED ──çıkış kararı──▶ CLOSING ──fill/ALGO_UPDATE──▶ CLOSED
     │                    │                        │                          │
     └─reject/expire──▶ CLOSED                     └─data bayat / kill ──▶ FROZEN (borsa koruması devrede, uygulama sessiz)
                          └─koruma ACK gelmezse T_protect içinde ──▶ EMERGENCY_CLOSE (reduceOnly MARKET)
```

- **PROTECTING:** giriş `ORDER_TRADE_UPDATE` ile FILLED olur olmaz SL ve TP algo emirleri gönderilir (iki ayrı `algoOrder.place`, ikisi de `closePosition=true`). Koruma ACK'i `T_protect` (config) içinde gelmezse pozisyon **derhal** reduceOnly MARKET ile kapatılır: korumasız pozisyon taşınmaz.
- **MANAGED:** her olayda (bar kapanışı, bookTicker, markPrice, tick) kurallar değerlendirilir.
- **FROZEN:** veri bayat ya da kill switch; uygulama emir göndermez, borsa SL/TP durur. Veri dönünce mutabakat (REST snapshot + open algo orders) ve MANAGED'a dönüş.
- Tek sahiplik: bir pozisyonun tüm emirlerini yalnızca `PositionManager` üretir; başka bileşen emir göndermez.

## 5. Katman 1 — borsa tarafı koruma mekaniği

- SL: `STOP_MARKET`, TP: `TAKE_PROFIT_MARKET`; `closePosition=true`, `workingType` ve `priceProtect` config.
- **`clientAlgoId` şeması (deterministik):** `f{pos_id}-{SL|TP}-v{n}`; `pos_id` = giriş `clientOrderId`'sinden türetilir; `n` her değiştirmede artar. Aynı `(pos_id, tür, n)` asla iki kez gönderilmez → idempotent yeniden deneme.
- **Değiştirme = önce yeni, sonra eski iptal.** Algo emir modify edilemez. Sıra: `place(v{n+1})` ACK → `cancel(v{n})`. Arada iki SL aynı anda açık kalır; ikisi de `closePosition` olduğu için tetiklenen ilki pozisyonu kapatır, ikincisi pozisyon kalmadığından işlem üretmez (`closePosition` yeni pozisyon açamaz — doğrulanmış semantik). Bu sıra **hiçbir an korumasız kalmaz**. İptal başarısızsa yeniden denenir; 200 koşullu emir limiti izlenir.
- **OCO yok (doğrulanmadı, varsayım: yok).** SL tetiklenince TP, TP tetiklenince SL uygulama tarafından iptal edilir (`ALGO_UPDATE` → `cancel`). Gecikme penceresinde diğer emir tetiklense bile pozisyon kapalı olduğundan ters pozisyon açılmaz. Faz 9'da testnet'te doğrulanacak; OCO benzeri bir mekanizma bulunursa ADR ile geçilir.
- **Auto-cancel** (`countdownCancelAll`) yalnızca giriş emirleri için düşünülür; algo emirlerle etkileşimi bilinmiyor → Faz 9'da test edilene kadar **hiç kullanılmaz**.

## 6. Katman 2 — uygulama tarafı kurallar (v1, en fazla 5, ağırlıksız)

Hepsi saf: `(position, market_view, state_label, now) -> ExitDecision | None`. Öncelik sırası sabit; ilk tetiklenen kazanır. Her parametre config'de, değerler Faz 3/4 replay'inden gelene kadar `null`.

| # | Kural | Tetik | Eylem | Parametre |
|---|---|---|---|---|
| R1 | **Yedek stop** | mark, SL seviyesini geçti ve `T_backup` içinde `ALGO_UPDATE`/fill gelmedi | reduceOnly MARKET | `T_backup` (≥ tepki p99 + pay; başlangıç bilinmiyor) |
| R2 | **Durum bozulması** | pozisyonun açıldığı durum ters durumla değişti (S1→S2, S2→S1) ya da S4 tükenme sinyali pozisyona ters | tam çıkış reduceOnly MARKET (ya da `priceMatch=OPPONENT` LIMIT, config) | `degrade_map` |
| R3 | **Kâr kilidi (ratchet)** | net gerçekleşmemiş kâr (maliyet düşülmüş, mark ile) ≥ `lock_trigger` | SL'yi `entry ± cost + lock_offset`'a taşı; sonra her `step` kadar lehte harekette SL'yi `trail_gap` geride tut; yalnızca lehte yönde hareket eder | `lock_trigger`, `lock_offset`, `step`, `trail_gap`, `min_replace_interval` |
| R4 | **Kısmi azaltma** | net kâr ≥ `tp1` | pozisyonun `tp1_frac`'ı reduceOnly MARKET; kalan için SL breakeven'a | `tp1`, `tp1_frac` (80 USDT'de `stepSize`/`minNotional` filtreleri kısmiyi engelleyebilir → REJECT durumunda kural pas geçilir) |
| R5 | **Zaman aşımı** | tutma süresi ≥ `max_hold` ve net kâr ≤ 0 | tam çıkış | `max_hold` (Faz 3 ufkuna bağlı) |

Notlar:
- R3 değiştirme sıklığı emir sayacına ve 200 koşullu limite bağlıdır; `step ≥ max(tick, maliyet)` ve `min_replace_interval` ile sınırlanır. Her değiştirme `place→cancel` sırasını izler.
- R2/R4/R5 çıkış emirleri her zaman `reduceOnly=true`; STP modu config (`EXPIRE_TAKER` başlangıç önerisi, doğrulanacak).
- Kurallar pozisyon açılırken **bilinen** SL/TP ile başlar (ADR 0004); statik TP tek çıkış değil, R3 ve R4 onu tamamlar.
- Kural sayısı 5'i geçmez; yeni kural = eski kuralın yerine.

## 7. Zaman ve olaylar

- Çekirdek yalnızca olayla çalışır (Faz 2). Zaman aşımı ve `T_backup` için gateway **periyodik tick olayı** üretir (config `tick_ms`, kayda da yazılır → replay'de aynı). Faz 2 "yapılmayanlar" listesindeki eksik burada kapanır.
- Tüm süreler `recv_ns`/tick ile; bar zamanı yalnızca durum etiketinde.

## 8. Muhasebe

- Gerçekleşmemiş PnL = yön × (mark − giriş) × miktar; **net** = PnL − giriş komisyonu − tahmini çıkış komisyonu − birikmiş funding − tahmini slippage. Kurallar net değeri okur, brütü değil.
- ROE = net / teminat (teminat = notional / kaldıraç). Karar eşikleri notional yüzdesiyle yazılır; kaldıraç yalnızca ROE raporunda.
- Gerçekleşen PnL Binance income kayıtlarından; iç hesapla sapma → alarm (Faz 5/8).

## 9. Yarış durumları ve idempotency

| Senaryo | Önlem |
|---|---|
| Borsa SL tetiklenirken uygulama da kapatıyor | uygulama emri `reduceOnly` → pozisyon kalmadıysa `-2022` ile reddedilir, ters pozisyon açılamaz; ret beklenen sonuçtur, hata değil |
| Emir cevabı kayboldu / 503 UNKNOWN | `clientOrderId`/`clientAlgoId` deterministik; `order.status` / `algoOrder` sorgusu ile mutabakat, sonra yeniden dene |
| Yinelenen `ORDER_TRADE_UPDATE` | `(orderId, tradeId)` ile dedupe |
| Kısmi dolum | pozisyon miktarı user data'dan; koruma emirleri `closePosition` olduğu için miktar bağımsız |
| `EXPIRED_IN_MATCH` (STP) | çıkış yeniden gönderilir, sayaç alarmı |
| Yeniden başlatma | açılışta REST ile pozisyon + open algo orders çekilir; iç state ile uyuşmazlıkta trading kilitli, pozisyon FROZEN |

## 10. Faz 4 kabul kriterleri (taslak)

1. Durum makinesi ve 5 kural saf; tüm parametreler config; hiçbir sabit yok.
2. Replay: Faz 3'ün geçen hücrelerinden üretilen girişlerle, (a) yalnızca statik SL/TP, (b) statik + R1–R5 karşılaştırılır. Raporda: net beklenti, **kârdan zarara dönen pozisyon oranı**, çıkış nedeni dağılımı, ortalama tutma süresi, emir değiştirme sayısı. Kapı: (b), (a)'ya göre kârdan zarara dönme oranını düşürür **ve** net beklentiyi düşürmez (maliyet dahil).
3. Hata enjeksiyonu: koruma ACK gecikmesi → EMERGENCY_CLOSE; SL tetik + uygulama çıkışı çakışması → tek kapanış; 503 → mutabakat.
4. Determinizm: aynı kayıt aynı çıkış dizisi.

## 11. Proje sahibine sorular (Faz 4 başında)

1. `trigger_price_source` için MARK_PRICE önerisi kabul mü?
2. R2 çıkışında MARKET mi, `priceMatch=OPPONENT` LIMIT mi (maliyet vs kesinlik)?
3. Kısmi azaltma 80 USDT notional'da filtrelere takılabilir (BTC minimum 78 USDT → kısmi imkânsız). R4 yalnızca filtre izin verdiğinde çalışsın mı, yoksa BTC için notional artırılsın mı?

## 12. Bu notta olmayanlar

- Sayısal eşikler: hiçbiri; Faz 3/4 replay'inden.
- Giriş mantığı (Faz 6), risk vetoları (Faz 5), canlı emir yolu (Faz 9).
- OCO varlığı ve `countdownCancelAll` × algo etkileşimi doğrulanmadı.
