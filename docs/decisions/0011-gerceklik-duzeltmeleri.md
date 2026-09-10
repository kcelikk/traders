# ADR 0011 — Mutlak kuralların ölçülebilir kurallara çevrilmesi

Tarih: 2026-09-10 · Durum: kabul edildi (proje sahibi: "hepsini öneri gibi uygula")

| Eski kural | Yeni kural |
|---|---|
| Unit economics tablosu tutmuyorsa mimariye devam etme (prompt 6.3) | Tablo bilgilendiricidir; kapı değildir. Maliyet her rapora dahil kalır. |
| Fast path'te hiçbir senkron iş 1 ms'yi geçmez | 1 ms **bütçe**dir: loop lag p99 ölçülür ve yayınlanır; bütçe aşımı alarm üretir, durdurmaz. GC/gzip kaynaklı seyrek tepeler kabul edilir, sayısı raporlanır. |
| Testnet'te en az 2 hafta hatasız | Hata sınıfları tanımlanır (beklenen: reconnect, `-2022`, `EXPIRED_IN_MATCH`, 429 geri çekilme; beklenmeyen: mutabakat uyuşmazlığı, korumasız pozisyon, ters pozisyon, kayıp emir). Kapı: Faz 9 test planının tamamı + ≥ 100 emir döngüsünde beklenmeyen hata 0. Süre şartı yok. |
| Paper trading minimum 4 hafta | 2 haftada ara rapor, 4 hafta hedef; devam kararı proje sahibinin. |
| Ağırlıklı skorlama / model v1'de yok | Yasak değil, koşul: her model walk-forward (zaman bazlı, görülmemiş veri) doğrulamasından ve ADR 0008 karar kuralından geçmeden karara bağlanmaz. Ağırlıklar config'de, seed'li, sürümlü. |
| En fazla 5 durum | Üst sınır 5 kalır; değişiklik ADR ister. |
| Sinyal ufku ≥ 10 × gecikme | Kalır; gecikme ölçülmüş p99 (≈ 1 s) → ufuk ≥ 10 s. |
| Faz 3 DUR kapısı | Kaldırıldı (ADR 0010). |

Değişmeyenler: doğrulanmamış API detayı kullanmama, look-ahead yasağı, maliyetsiz sonuç raporlamama, borsa tarafı koruma, kalıcı kill switch, açılışta mutabakat, determinizm, anahtar güvenliği, canlı yol için onay.
