# ADR 0020 — Emir kaydı, çıkış kilidi, sahipsiz emir politikası ve `-2022` (Gate 3)

Tarih: 2026-09-12 · Durum: kabul edildi · Kapsam: Gate 3b + 3c + 3d · **hash-nötr**

Bu ADR `docs/design/faz4-cikis-kurallari.md` §9'daki `-2022` politikasını **supersede eder**.
Eski ADR'ler silinmez.

## Bağlam

Borsa, emir durumunu user data akışıyla bildirir; REST cevabı volatil piyasada gecikebilir. Sistem
bugüne kadar yalnız REST ack'ine bakıyordu: private akış hiç tüketilmiyordu
(`fbot/testnet/main.py:on_user_event` çağıransızdı). Gate 3b'de akış shadow modda bağlandı ve
gerçek çerçeveler kaydedildi (`docs/gate3-userdata-gozlem.md`).

Kayıt üzerinden dört yapısal boşluk çıktı:

1. **`pos_id` taşınmıyor.** User data çerçevesi yalnız `clientOrderId` taşır; çekirdeğin `_exec`
   dalları ise `pos_id` bekliyordu. Eşleme I/O kenarında yapılsaydı replay'de yeniden kurulamaz,
   determinizm kırılırdı.
2. **`trade_id` okunmuyordu** → `OrderBook.apply` dedupe için onu arıyor, bulamadığı için tekrar
   bastırma sessizce çalışmıyordu (3b'de kapatıldı).
3. **Aynı anda iki çıkış emri üretilebiliyordu.** Bir `reduceOnly` market emri uçarken ikincisi
   üretilirse ya `-2022` döner ya da kapanışla yarışıp ters pozisyon açar.
4. **`-2022` sessizce yutuluyordu** (`EXPECTED_CODES` içindeydi). Gate 0 §6: bu kod tek başına
   "pozisyon zaten kapalı" anlamına gelmez.

## Karar

### 1. `fbot/core/oms.py` — saf emir kaydı, çekirdekte

`clientOrderId → (pos_id, rol, sembol, durum, orderId)`. Rol: `entry` / `exit` / `protective` /
`partial`. Kayıt `CoreState`'in parçasıdır ve üretilen her emir **tek bir yerde**
(`Engine._register_orders`) kaydedilir; aynı olay dizisi aynı kaydı üretir.

Çözüm sırası: önce kayıt, sonra kimlik grameri (`fbot/core/ids.py`), ikisi de tutmazsa **bilinmiyor**.
Kayıtta olmayan bir emrin olayı yok sayılır: hesaptaki yabancı emrin dolumu bizim pozisyonumuz değildir.

**Mantıksal niyet defteri:** `{pos_id}:{rol}` anahtarı terminal olmayan bir emre bağlıysa ikinci
emir üretilmez. Gate 0 §5 gösterdi ki borsa aynı `clientOrderId` ile ikinci emri reddetmiyor,
ikisi de doluyor — dedupe borsanın reddine dayanamaz.

Durum ilerler, geri gitmez (`_RANK`). Cevapsız kalan emir `order_ack_ttl_ms` (30 s) sonunda
`UNKNOWN`a düşer: sessizce `PENDING` kalmak, mutabakatın çözmesi gereken durumu görünmez kılar.

### 2. Çıkış kilidi (`exit_in_flight`) + TTL

Bir mantıksal çıkış terminal olmadan ikincisi üretilmez. Kilit, çıkış emri dolunca / iptal olunca
açılır; cevap hiç gelmezse `exit_ttl_ms` (30 s) sonunda açılır — aksi hâlde pozisyon kapatılamaz
hâle gelir.

Tam çıkış miktarı da **filtreye uyar**: `step_size`'a yuvarlanır, `min_qty` altındaki artık için
emir üretilmez (borsa tarafı koruma devrede kalır, durum mutabakata bırakılır).

Koruma sürümleri (`sl_version`/`tp_version`) pozisyon açılırken kayıttan geri yüklenir: yeniden
başlatmadan sonra sürüm 1'e dönerse yeni `clientAlgoId` eskisiyle çakışır ve borsadaki koruma emri
sahipsiz kalır.

### 3. Sahipsiz koruma emri: **dry-run varsayılan**, sahiplik gramerle

`reconcile` artık iptal komutu üretir ama **yalnız bizim kimlik gramerimize uyanlar** için
(`{tag}{L|S}{hash}-{SL|TP}-v{n}`). Uymayanlar `foreign_untouched` olarak raporlanır ve dokunulmaz;
strateji etiketi verilmezse hiçbir iptal üretilmez (fail-closed).

`[reconcile] orphan_cancel = "dry_run"` varsayılandır: plan olaya yazılır, borsaya istek gitmez.
`apply` moduna geçiş bir hafta gözlem **ve proje sahibi onayı** gerektirir; borsada bizim olmayan
bir değişiklik yapmak geri alınamaz.

### 4. `-2022` artık "beklenen ret" değil

`EXPECTED_CODES`'tan çıkarıldı, `UNKNOWN_EXECUTION`'a alındı. Gelirse emir `UNKNOWN` işaretlenir,
`needs_reconcile` ile mutabakat istenir; pozisyon durumu borsadan doğrulanır. Sessizce yutmak,
gerçekten açık kalmış bir pozisyonu kapandı sanmak demekti.

`-2011` (unknown order), `-2013`, `-4137`, `-4138`, `-1111`, `-4164`, `-5021`, `-5022` beklenen
ret olarak kalır: bunlar yarış durumunun normal sonucudur ve yürütme belirsizliği yaratmaz.

### 5. Private akış shadow'da kalır

Çekirdek bugün user data tüketmiyor; `Engine.step` `private` kategorisini sayıp geçiyor.
`[userdata] mode = "active"` ile tüketim açılır — bu **ayrı bir onay kapısıdır**, bu ADR'nin
parçası değildir. Geri alma: `[userdata] enabled = false`.

## Sonuçlar

- Golden hash'lerin ikisi de değişmedi; Gate 3 hash-nötr kaldı. 579 → 612 test.
- `OrderStatus.UNKNOWN` eklendi; terminal koruması korundu (UNKNOWN terminalin altında).
- Testnet süreci kill switch dosyasını artık periyodik okuyor (paper'da vardı, testnet'te yoktu).
- **Açık kalan:** korumasız pozisyon onarımı, balance/margin snapshot'ı, HEDGE'te ARM reddi,
  `income()` ile gerçek komisyon aktarımı. Bunlar Gate 3'ün kalan adımları ve Gate 4.
- **Ölçülmedi:** dolum çerçevesinden çekirdeğe gecikme, dup `tradeId` sayısı, UNKNOWN kapanma
  süresi. Hepsi gerçek dolum gerektirir; ayrı onayla yapılacak.
