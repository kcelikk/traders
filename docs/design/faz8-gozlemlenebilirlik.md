# Faz 8 tasarım notu — gözlemlenebilirlik

Tarih: 2026-09-10 · Durum: tasarım notu, kod yok. Prometheus + Grafana + yapılandırılmış log (kilitli).

## 1. Metrik kataloğu (BÖLÜM 10 → kaynak)

| Metrik | Tip | Kaynak | Etiket |
|---|---|---|---|
| `ws_lag_ms` (recv − E) | histogram | gateway, her çerçeve (örnekli) | category, stream |
| `loop_lag_ms` | histogram | Faz 1 `stats` görevi | process |
| `decision_latency_ms`, `risk_latency_ms` | histogram | çekirdek step süresi (I/O kenarında ölçülür) | — |
| `order_ack_ms`, `fill_latency_ms` | histogram | execution adapter (paper: simüle; canlı: WS API cevabı, `ORDER_TRADE_UPDATE`) | type |
| `events_dropped_total`, `events_dup_total`, `events_out_of_order_total` | counter | integrity (aggTrade `a`, bookTicker `u`, depth `pu`) | stream |
| `ws_reconnects_total`, `orderbook_resync_total` | counter | gateway, order book | category / symbol |
| `rate_limit_used` | gauge | header'lar / WS `rateLimits` (gerçek değer) | limiter (weight_1m, orders_10s, orders_1m) |
| `staleness_ms` | gauge | Faz 2 bayatlık | category |
| `open_positions`, `gross_exposure_usdt`, `beta_exposure_usdt` | gauge | Risk Engine state | — |
| `realized_pnl_usdt`, `unrealized_pnl_usdt`, `drawdown_pct` | gauge | muhasebe (income + mark) | — |
| `cost_commission_to_gross`, `cost_total_to_capital`, `net_per_trade_usdt` | gauge | maliyet sürüklenmesi (6.4) | window |
| `warmup_ready`, `kill_switch_active`, `reconciliation_ok` | gauge (0/1) | Risk Engine | symbol / — |
| `state_transitions_total` | counter | Market State Engine | symbol, from, to |
| `exit_reason_total`, `profit_to_loss_total` | counter | Position Manager | reason |

Hot path metrik toplamaz: çekirdek `Command`/olay üretir, sayaçlar process 4'te bus'tan türetilir; process 1 yalnızca kendi `loop_lag` ve bağlantı sayaçlarını yerel tutar ve periyodik `stats` olayı yayar.

## 2. Bus kararı (Faz 8 ADR'si)
Seçenekler: (a) stdlib Unix domain socket üzerinden JSONL fire-and-forget (bağımlılık yok; abone yoksa düşürülür); (b) ZeroMQ PUB/SUB (bağımlılık, olgun); (c) Redis Streams (yalnızca ölçülmüş ihtiyaçta, kilitli). Öneri: (a) ile başla, yayın maliyetini `loop_lag` ile ölç; 1 ms bütçesini aşarsa (b). Bus **hot path'te değildir**: yayın `queue.put_nowait`, gönderim ayrı görev.

## 3. Bileşenler
- Process 4 `api/metrics`: bus abonesi; Prometheus `/metrics` (stdlib `http.server` + elle format, ya da `prometheus_client` — yeni bağımlılık, ADR); `/status` JSON (faz, mod, kill switch, mutabakat, ısınma, açık pozisyonlar).
- Compose: `prometheus`, `grafana` servisleri (image çekimi; sistem kurulumu yok). Dashboard'lar repo'da JSON olarak (`infra/grafana/`).
- Alarmlar: Prometheus kuralları → Alertmanager → kanal (**proje sahibi kararı**: Telegram? e-posta?). Zorunlu alarmlar: kill switch, mutabakat uyuşmazlığı, bayatlık, 429/418, koruma ACK gecikmesi, maliyet sürüklenmesi eşikleri, loop lag p99 > bütçe, disk doluluk.
- Log: JSON satır, her kayıtta `config_version`, `git_sha`, `correlation_id`; hot path'te log yazımı yok (olaylar bus üzerinden loglanır).

## 4. Kabul kriterleri (taslak)
1. BÖLÜM 10'daki her metrik `/metrics`'te ve dashboard'da; eksik varsa listelenir.
2. Bus yayınının hot path maliyeti ölçülür (`loop_lag` öncesi/sonrası) ve raporlanır.
3. Alarm kuralları için sentetik tetik testi (her alarm en az bir kez yapay olarak tetiklenir).
4. Metrik process'i çökse trader etkilenmez (test).

## 5. Sorular
1. Alarm kanalı?
2. `prometheus_client` bağımlılığı kabul mü, yoksa elle format mı?

## 6. Olmayanlar
Eşik değerleri; retention ve disk planı (ölçümle).
