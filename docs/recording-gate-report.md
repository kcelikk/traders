# Kayıt doğrulama — `rec-72h`

Kapsam: **3.34 saat** (1789027420101177877 → 1789039441836294776 ns). Başlangıç sayısı: 1. Dosya: 4 (manifestte 3, açık 1). Disk: 774.1 MB gzip.

## Kapı kriterleri

| Kriter | Değer | Durum |
|---|---|---|
| seq boşluğu | 0 (eksik 0) | OK |
| seq tekrarı | 0 | OK |
| SHA-256 / sayım uyuşmazlığı | 0 | OK |
| kesik gzip | 1 | UYARI (açık dosya olabilir): events-20260910T1100-11723975.jsonl.gz |
| kuyruk taşması (dropped) | 0 | OK |
| süre ≥ 1 saat (proje sahibi kararı 2026-09-10; eski kural 72 saat) | 3.34 | HENÜZ DEĞİL |

## Olaylar

Toplam olay: 14054922. Kontrol olayları: connect=2, run_start=1, snapshot=200, stats=1194
En büyük olaysız aralık: 0.48 s (bitiş 1789027420976335736)
Bağlantı kurulumları: 2; bayatlık olayları: 0; snapshot OK/hata: 200/0
Loop lag (10 s pencerelerinin p99'ları): p50=1.62 ms, p99=8.76 ms; mutlak maks 95.84 ms; kuyruk maks 569

## Stream bütünlüğü

| Stream | olay | zincir kopuşu | E geriye gidiş | parse hatası |
|---|---|---|---|---|
| bnbusdt@aggTrade | 25804 | 0 | 0 | 0 |
| bnbusdt@bookTicker | 432827 | 0 | 0 | 0 |
| bnbusdt@depth@100ms | 108279 | 0 | 0 | 0 |
| bnbusdt@forceOrder | 7 | 0 | 0 | 0 |
| bnbusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| btcusdt@aggTrade | 105021 | 0 | 0 | 0 |
| btcusdt@bookTicker | 3297439 | 0 | 0 | 0 |
| btcusdt@depth@100ms | 117845 | 0 | 0 | 0 |
| btcusdt@forceOrder | 72 | 0 | 0 | 0 |
| btcusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| dogeusdt@aggTrade | 17758 | 0 | 0 | 0 |
| dogeusdt@bookTicker | 621648 | 0 | 0 | 0 |
| dogeusdt@depth@100ms | 100535 | 0 | 0 | 0 |
| dogeusdt@forceOrder | 20 | 0 | 0 | 0 |
| dogeusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| ethusdt@aggTrade | 82412 | 0 | 0 | 0 |
| ethusdt@bookTicker | 2604935 | 0 | 0 | 0 |
| ethusdt@depth@100ms | 117539 | 0 | 0 | 0 |
| ethusdt@forceOrder | 58 | 0 | 0 | 0 |
| ethusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| hypeusdt@aggTrade | 61208 | 0 | 0 | 0 |
| hypeusdt@bookTicker | 767094 | 0 | 0 | 0 |
| hypeusdt@depth@100ms | 106350 | 0 | 0 | 0 |
| hypeusdt@forceOrder | 19 | 0 | 0 | 0 |
| hypeusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| iostusdt@aggTrade | 269792 | 0 | 0 | 0 |
| iostusdt@bookTicker | 928864 | 0 | 0 | 0 |
| iostusdt@depth@100ms | 112889 | 0 | 0 | 0 |
| iostusdt@forceOrder | 206 | 0 | 0 | 0 |
| iostusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| nearusdt@aggTrade | 12965 | 0 | 0 | 0 |
| nearusdt@bookTicker | 374986 | 0 | 0 | 0 |
| nearusdt@depth@100ms | 93153 | 0 | 0 | 0 |
| nearusdt@forceOrder | 15 | 0 | 0 | 0 |
| nearusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| solusdt@aggTrade | 33182 | 0 | 0 | 0 |
| solusdt@bookTicker | 923028 | 0 | 0 | 0 |
| solusdt@depth@100ms | 111318 | 0 | 0 | 0 |
| solusdt@forceOrder | 18 | 0 | 0 | 0 |
| solusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| xrpusdt@aggTrade | 30034 | 0 | 0 | 0 |
| xrpusdt@bookTicker | 829783 | 0 | 0 | 0 |
| xrpusdt@depth@100ms | 114210 | 0 | 0 | 0 |
| xrpusdt@forceOrder | 29 | 0 | 0 | 0 |
| xrpusdt@markPrice@1s | 12021 | 0 | 0 | 0 |
| zecusdt@aggTrade | 189649 | 0 | 0 | 0 |
| zecusdt@bookTicker | 1230407 | 0 | 0 | 0 |
| zecusdt@depth@100ms | 111848 | 0 | 0 | 0 |
| zecusdt@forceOrder | 69 | 0 | 0 | 0 |
| zecusdt@markPrice@1s | 12021 | 0 | 0 | 0 |

## Saat bazında olay sayısı

| saat (UTC) | olay |
|---|---|
| 2026-09-10T08 | 3471623 |
| 2026-09-10T09 | 4186333 |
| 2026-09-10T10 | 4066018 |
| 2026-09-10T11 | 2330948 |

## Bağlantı olayları (ilk 30)

- 1789027420976335736 market connect #1
- 1789027421060198258 public connect #1
