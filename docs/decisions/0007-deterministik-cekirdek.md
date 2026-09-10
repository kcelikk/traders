# ADR 0007 — Faz 2: deterministik çekirdek, replay harness, maliyet modeli

Tarih: 2026-09-10 · Durum: kabul edildi (Faz 2 başlangıcı)

## Bağlam
Rule Zero (CLAUDE.md): aynı kayıt iki kez oynatıldığında bit-eşit karar dizisi. Faz 2'de strateji yok; çekirdek yalnızca piyasa görünümünü (best bid/ask, son işlem, mark/funding, 1 dk bar) ve kategori bayatlığını türetir. Determinizm kanıtı bu türetilmiş komut dizisinin hash'idir.

## Kararlar
1. **Saf çekirdek imzası:** `Engine.step(state, event, now_ns) -> (state, commands)`. Çekirdek modülleri (`fbot/core/*`, `fbot/costs.py`, `fbot/clock.py`) import düzeyinde `time, datetime, random, os, sys, socket, http, urllib, asyncio, threading, subprocess, pathlib, io, gzip, websockets` içermez; bu bir testle (`tests/test_purity.py`, AST taraması) zorlanır.
2. **State sahipliği:** `state` nesnesi yalnızca çekirdek tarafından değiştirilir ve `step` aynı nesneyi döndürür (yerinde güncelleme). Fonksiyonel saflık, "dış girdi yalnızca (state, event, now_ns)" ve "yan etki yok" anlamındadır; nesne kopyalama maliyeti 2.000+ olay/s'de gereksiz. Dış kod state'i değiştirmez.
3. **Saat:** çekirdek `now_ns` parametresini alır; replay'de `event.recv_ns`, canlıda duvar saati. `fbot/clock.py` yalnızca protokol ve `ReplayClock` içerir; `WallClock` I/O kenarında (`fbot/gateway/`).
4. **Zaman damgası seçimi:** bar kovası aggTrade `T` (işlem zamanı) ile; bayatlık `recv_ns` ile. `E` yalnızca gecikme metriği. Gerekçe: `T` eşleşme anıdır ve replay'de sabittir; `recv_ns` alım anıdır ve bayatlık onunla ölçülür.
5. **Bar üretimi:** 1 dk bar, işlem zamanı kovasıyla; yeni kovaya düşen ilk işlem önceki barı kapatır (`BarClosed`). İşlemsiz dakikada bar üretilmez (boşluk deterministiktir). Fiyat ve miktar `Decimal`; float yok.
6. **Komutlar:** `BarClosed`, `StalenessChanged`. Faz 4+: `PlaceOrder`, `CancelOrder`, `PlaceAlgo`. Her komut `canonical()` ile deterministik baytlara serileştirilir; replay hash'i `sha256(seq || canonical)` zinciridir.
7. **Replay harness:** kayıt dizinini okur, `ReplayClock`'u `recv_ns` ile ilerletir, `Engine.step` çağırır, komut akışını hash'ler. Kaydedici ile aynı satır formatı; farklı format yok.
8. **Maliyet modeli (`fbot/costs.py`):** komisyon (maker/taker, BNB indirimi), funding (pozisyon yönü × oran × notional), slippage (defter yürüyüşü). Oranlar `CostConfig` ile dışarıdan gelir; hard-code yok. Değerler `Decimal`.
9. **Execution arayüzü:** `ExecutionAdapter` protokolü; `PaperExecutionAdapter` ve `ReplayExecutionAdapter` komutları kaydeder; `LiveExecutionAdapter` her çağrıda `RuntimeError` fırlatan korumalı stub — proje sahibi onayına kadar.
10. **Determinizm testi:** aynı fixture iki **ayrı process**'te oynatılır, hash'ler eşit olmalı; tek olayın tek baytı değiştirilince hash değişmeli (negatif test). `make test-determinism`.

## Reddedilenler
- Immutable state + `dataclasses.replace`: 2.000 olay/s'de gereksiz kopya; determinizme katkısı yok.
- Bar için `recv_ns`: canlı/replay'de aynı olsa da işlem zamanı piyasa gerçeğine daha yakın; `T` seçildi.
- Float fiyat: tick yuvarlama ve eşitlik karşılaştırmaları için `Decimal` şart.

## Sonuçlar
- Faz 3 araştırması bar ve piyasa görünümü komutlarını tüketir.
- Faz 4 çıkış kuralları `step` içine eklenir; imza değişmez.
- Bilinmeyen: replay hızı (olay/s). Ölçülecek ve raporlanacak.
