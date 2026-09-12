# ADR 0022 — Strateji platformu: manifest, terfi zinciri, kira ve iki katmanlı risk (Gate 5)

Tarih: 2026-09-12 · Durum: kabul edildi · Kapsam: Gate 5

## Bağlam

Bugüne kadar tek bir gömülü strateji vardı: `fbot/core/decision.py`. Dört tur ölçümde 3.960
birleşim denendi (`docs/research/strateji-v1.md`); bu arayış, stratejinin **versiyonlanabilir ve
atıflandırılabilir** olmadığı sürece sürdürülebilir değil. Ayrıca birden fazla strateji aynı
sembolde giriş üretebilir ve bugünkü `pending_entries` sahibi bilmiyor.

## Karar

### 1. Strateji sözleşmesi saf kalır

`fbot/strategy/base.py`: `on_bar(ctx) -> list[Intent]`. I/O yok, saat yok, emir yok. Strateji yalnız
**niyet** üretir; niyetin emre dönüşmesi risk motorundan ve emir yolundan geçer. `tests/test_purity.py`
bu paketi zaten tarıyor.

### 2. Manifest + terfi zinciri, fail-closed

`strategies/<id>/manifest.toml`: kimlik, sürüm, parametreler, sembol evreni, risk bütçesi,
`allowed_modes`, `promotion_state`.

Terfi: `draft → replay_ok → paper_ok → testnet_ok → live`. Her mod bir alt adımı şart koşar
(`paper` için `replay_ok`, `testnet` için `paper_ok`, `live` için `testnet_ok`). `allowed_modes`
içinde `live` varken `promotion_state` `live` değilse manifest **yüklenmez**.

**Engellenen strateji gömülü motora düşmez.** Kayıt defteri varken hiçbir strateji o modda yetkili
değilse çekirdek niyet üretmez (`strateji_yetkili_degil`). Aksi hâlde terfi kapısı anlamsız olurdu:
aynı mantık kapıyı atlayarak çalışırdı.

Geri alma: `[strategy] enabled = []` → kayıt defteri kurulmaz, çekirdek gömülü karar motoruyla
çalışır (Gate 4 davranışı).

### 3. `fbot/core/lease.py` — sembol kirası

`pending_entries`'in genelleştirilmiş hâli, yeni kavram değil. K7 semantiği **değişmez**; yalnız
"meşgul" sorusunun cevabı sahibi de söyler. Kira dolumda pozisyona bağlanır (bağlıyken TTL işlemez)
ve **pozisyon kapandıktan ve koruma emirleri terminal olduktan sonra** bırakılır: erken bırakılan
kira, ilk pozisyonun korumaları hâlâ borsadayken ikinci girişe kapı açar.

TTL zorunludur; süresiz kira, Gate 2.0'da kapatılan sızıntının tekrarı olur.

### 4. İki katmanlı risk

Strateji bütçesi (`max_positions`, `gross_cap_usdt`) global K1–K18'in **altında** ikinci kapıdır;
global her zaman kazanır. `K19_strategy_gross_cap` yumuşaktır (küçültür, K8 gibi),
`K19_strategy_max_positions` serttir (K6 gibi).

### 5. İlk plugin mevcut mantığı **sarmalar**

`fbot/strategy/v1_state_cell.py` `decide_explain`'i çağırır, yeniden yazmaz.

## Parite — gate çıkış koşulu

`make parity`: aynı senaryo iki kez koşar, biri gömülü karar motoruyla biri registry üzerinden.

```
gomulu : hash 3b75da42… · 228 komut
plugin : hash 3b75da42… · 228 komut
esit   : true
```

Karşılaştırılan şey niyet değil, **çekirdeğin ürettiği komut dizisidir**: soyutlama zincirin hiçbir
halkasını değiştirmiyor. İki golden de değişmedi.

## Sonuçlar

- 675 → 705 test.
- `v1_state_cell` bugün `replay_ok`: replay ve paper'da çalışabilir, **testnet'te çalışamaz**.
  Testnet servisinde kayıt defteri stratejiyi engelliyor ve bunu `blocked` alanında söylüyor.
  Davranış değişmiyor çünkü `allowed_cells` zaten boş.
- **Ölçülmedi:** strateji × versiyon bazında PnL atfı (kapanan işlem yok), kira çakışma sayısı
  (tek strateji), registry açıkken `Engine.step` ek maliyeti (ölçüm sonraki adım).
- Terfi `paper_ok`'a yükseltilmesi paper kanıtı ister; bu bir proje sahibi kararıdır.
