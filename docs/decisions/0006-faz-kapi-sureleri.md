# ADR 0006 — Faz kapı süreleri: 72 saat → 1 saat

Tarih: 2026-09-10 · Durum: kabul edildi (proje sahibi kararı)

## Bağlam
Prompt Faz 1 kapısı için "en az 72 saat kesintisiz kayıt" istiyordu. Proje sahibi bu süreyi yersiz buldu: "72 saat kuralı yersiz. kural 1 saat olarak güncellensin." Faz 0 gecikme ölçümü için prompt zaten "en az 1 saat" diyor.

## Karar
- Faz 1 kapısı: **≥ 1 saat** kesintisiz kayıt + bütünlük raporu. Recorder container'ı durdurulmaz; kayıt Faz 3 araştırması için birikmeye devam eder.
- Faz 0 kapısı: 1 saatlik ara rapor kapıyı karşılar; 24 saatlik ölçüm arka planda tamamlanır ve `docs/latency-baseline.md` güncellenir. Bayatlık eşiği ve `recvWindow` gibi parametreler 24 saatlik sonuçla kesinleşir.
- İzleyiciler en fazla 1 saat sınırlı (proje sahibi kararı, aynı gün).

## Sonuçlar
- Faz 1 kapı raporu: `docs/recording-gate-report.md` (3.5 saat, 2026-09-10).
- Faz 2 aynı gün başlar.
- Risk: 1 saatlik pencere gün içi ve funding saatlerindeki davranışı kapsamaz; bu boşluk süregelen kayıt ve 24 saatlik ölçümle kapatılır, kapı açılışı için engel sayılmaz.
