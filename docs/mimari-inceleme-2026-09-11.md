# Mimari inceleme — event-driven hot path ve pozisyon yönetimi

Tarih: 2026-09-11 · Kapsam: yalnızca inceleme, kod değiştirilmedi.
Kaynak: `fbot/` ağacı, `config/*.toml`, `docker-compose.yml`.

Hedef sorusu: *market datası işlenirken açık pozisyonlar bağımsız ve eşzamanlı izleniyor mu; bir
TP/SL/trailing/risk koşulu gerçekleştiğinde emir gönderimi en kısa yoldan başlıyor mu?*

---

## 1. Process / thread / async topology

**Process'ler** (`docker-compose.yml`): `fbot-recorder`, `fbot-paper`, `fbot-testnet`; ayrıca
systemd altında `fbot-console`.

Hepsi **tek thread, tek asyncio döngüsü** (`asyncio.run(...)`, `fbot/recorder/main.py:229`).
uvloop **YOK**, varsayılan `asyncio` event loop.

Recorder process'indeki task'lar (`Recorder.main`, satır 198–200): `writer_task`, kategori başına
`CategoryConnection.run` (2 adet), `snapshot_task`, `staleness_task`, `stats_task`, `tick_task`.
Toplam 7 coroutine. Paper/testnet buna ek olarak `paper_status_task`
(`fbot/paper/main.py:78`, `stats_task` ile `gather` edilerek).

**Market-data I/O ile strategy kernel aynı thread'de: EVET.** `CategoryConnection.run` içinde
`on_frame(...)` senkron çağrılıyor (`ws_category.py:65`), o da `Recorder.emit`
(`recorder/main.py:76`), o da satır 85'te doğrudan `self.trader.on_event(ev, ev.recv_ns)`
çağırıyor. Çekirdek, WS receive döngüsünün içinde, aynı stack'te koşuyor.

**Disk/SQLite/gzip hot-path'i bloke edebilir mi: KISMEN.**

- gzip yazımı kuyruk arkasında, ayrı task: `writer_task` (satır 100) `queue.get()` ile. Hot
  path'te değil.
- **SQLite hot path'te.** `PaperTrader._step` her adımda `_record_verdicts()` ve
  `_record_positions()` çağırıyor (`paper/trader.py:90–91`), bunlar `store.record_position` ile
  SQLite'a yazıyor. `emit → on_event → _step` zinciri WS thread'inde olduğu için **her market
  olayında SQLite insert** çalışıyor.
- REST çağrıları `asyncio.to_thread` ile ayrılmış (`snapshot_task`, satır 118). Ama testnet emir
  gönderimi `to_thread` **kullanmıyor**: `TestnetAdapter.submit → TestnetClient.signed →
  http.client.HTTPSConnection` senkron, event loop'u bloke eder.

---

## 2. Market data ingestion

**Connection sayısı: trading process başına 2.** `Recorder.main` satır 194–197,
`for cat in ("public", "market")`. Üç process birlikte Binance'a **6 bağlantı** açıyor.

URL: `wss://fstream.binance.com/{cat}/stream?streams=...` (satır 195).

**Stream dağılımı** (`config/recorder.toml`):

| Kategori | Stream'ler |
|---|---|
| `/public` | `{s}@bookTicker`, `{s}@depth@100ms` |
| `/market` | `{s}@aggTrade`, `{s}@markPrice@1s`, `{s}@forceOrder` |

10 sembol × 2 = 20 public stream, 10 × 3 = 30 market stream, tek birleşik bağlantıda.

**Kim alıyor:** hepsini `CategoryConnection.run`'daki `async for raw in ws` alıyor
(`ws_category.py:58`). Stream ayrımı yok, tek döngü.

**Reconnect:** `CategoryConnection.run` while döngüsü, üstel geri çekilme
`backoff_initial_s=1.0 → backoff_max_s=30.0` (satır 82). Resubscribe **YOK**, çünkü stream listesi
URL'in içinde; yeniden bağlantı aynı stream'leri açıyor. Ayrıca `Recorder.staleness_task`
(satır 131) eşik aşımında `conn.force_reconnect("stale")` çağırıyor.

**Event alındığında ilk fonksiyon:** `CategoryConnection.run` içindeki
`self.on_frame(raw, recv_ns, mono_ns)` → `Recorder.on_frame_for.<locals>.on_frame` (satır 94) →
`Recorder.emit`.

---

## 3. Event ordering

**Sequence:** `fbot/sequencer.py`, `Sequencer.next`. Tek yerde veriliyor: `Recorder.emit` satır 78.

**Global, sembol başına DEĞİL.** `Sequencer.last_seq` tek sayaç. Public, market, ctrl ve exec
olayları aynı diziye giriyor.

**10 sembol tek queue/worker üzerinden mi: EVET.** İki WS bağlantısı var ama ikisi de aynı
`emit`'e, aynı `Sequencer`'a, aynı event loop'a gidiyor.

**Head-of-line blocking: EVET, oluşabilir.** Bir sembolde burst olduğunda
`emit → trader.on_event → Engine.step` zinciri senkron çalıştığı için diğer sembollerin
çerçeveleri `ws.recv` kuyruğunda (`max_queue=4096`, `ws_category.py:22`) bekler. Sembol shard'ı
**YOK**.

---

## 4. Queue / backpressure

| Yapı | Tip | Max | Producer | Consumer | Dolunca |
|---|---|---|---|---|---|
| `Recorder.queue` (`main.py:64`) | `asyncio.Queue` | 500.000 | `emit` | `writer_task` | `QueueFull` → `self.dropped += 1`, olay **düşürülür** (satır 81–82) |
| `websockets` iç kuyruğu | `max_queue` | 4096 | soket | `async for raw in ws` | kütüphane geri basınç uygular |
| `SimExecutor.pending_orders` / `.triggered` | `list` | sınırsız | `submit` | `poll` | — |
| `CoreState.last_verdicts` | `list`, `del [20:]` | 20 | `_decide` | konsol | eskiler silinir |

**Trader kuyruk arkasında DEĞİL.** `emit` önce `queue.put_nowait` yapıyor, sonra
`trader.on_event` çağırıyor. Kuyruk dolsa bile trader olayı görür. Kuyruk düşmesi **yalnızca diske
yazmayı** etkiler, kararı etkilemez.

**Drop edilebilenler:** yalnızca disk kaydı, kuyruk 500.000'i aşarsa.

**Order/fill lossless mı:** paper'da evet (`SimExecutor` bellekte). Testnet'te **HAYIR** — user
data stream bağlı olmadığı için fill olayları hiç alınmıyor (bkz. §8).

---

## 5. Trading hot path

Tek bir `aggTrade` için gerçek çağrı zinciri:

```
websockets  async for raw in ws                 ws_category.py:58
→ CategoryConnection.run: recv_ns = time.time_ns()          :59
→ Recorder.on_frame_for.<locals>.on_frame       recorder/main.py:94
→ fbot.events.stream_of(raw)                    events.py:50   [json.loads #1]
→ Recorder.emit                                 recorder/main.py:76
   → Sequencer.next                             sequencer.py:13
   → self.queue.put_nowait(ev)                  (writer'a)
   → PaperTrader.on_event                       paper/trader.py:52
      → PaperTrader._step                                   :65
         → Engine.step                          core/engine.py:69
            → json.loads(ev.raw)                          :92   [json.loads #2]
            → Engine._route                               :180
               → SymbolMarket.on_agg_trade      core/market.py
               → (bar kapandıysa) Engine._on_bar_state     :210
                  → SymbolStateEngine.on_bar_cmds
                  → BetaTracker.on_bar
                  → Engine._decide                        :230
                     → decision.decide_explain  core/decision.py:57
                     → risk.assess              core/risk.py
                     → PlaceOrder(...)          core/commands.py
            → Engine._staleness                           :299
            → Engine._apply_freeze                        :155
         → (komut döngüsü) sim.submit / adapter.submit    trader.py:77
         → store.record_order (SQLite)                    trader.py:82
      → PaperTrader._feed_sim_from                        :93
      → PaperTrader._drain_sim                            :150
```

Testnet'te `sim.submit` yerine `TestnetTrader._send` (`testnet/main.py:63`) →
`TestnetAdapter.submit` → `TestnetClient.place_order` → `http.client` senkron POST.

---

## 6. Position management — en kritik bölüm

**Açık pozisyon varken yeni market event'i geldiğinde Position Manager otomatik çalışıyor mu:
HAYIR.**

`Engine.step` içinde `_tick_positions` **yalnızca** şu koşulda çağrılıyor
(`core/engine.py:82–86`):

```python
elif ev.stream == "tick":
    cmds += self._staleness(state, now_ns)
    self._apply_freeze(state)
    cmds += self._tick_positions(state, now_ns)
    return state, cmds
```

Market olayları (`else` dalı, satır 89–99) yalnızca `_route` çağırıyor. `_route` içinde `aggTrade`
için yapılan tek şey `m.on_agg_trade(d)`, yani bar inşası. **Pozisyon kuralları çalışmıyor.**

`ctrl/tick` olayları `Recorder.tick_task` (satır 147) tarafından `tick_ms = 1000` ile üretiliyor.
Yani **R1–R5 saniyede bir değerlendiriliyor.**

### Örnek: entry=100, TP=+%5, aggTrade 105'e geldi

105'lik aggTrade olayından sonra çağrılanlar:

```
on_frame → emit → trader.on_event → _step → Engine.step
  → _route → SymbolMarket.on_agg_trade   (yalnızca bar günceller)
  → _staleness, _apply_freeze
  → SON. Komut YOK.
```

**SELL emri üretilmez.** Üstelik `_tick_positions` çalışsa bile TP kontrolü yapmaz:
`PositionManager.on_tick` (`core/position.py:166`) TP eşiğini hiç okumuyor. Tetikleyiciler `mark`
fiyatı ve şunlar: koruma zaman aşımı, R2 durum bozulması, R1 yedek stop (yalnızca **SL** geçilince),
R5 zaman aşımı, R4 kısmi azaltma, R3 trailing.

**TP tamamen borsa tarafında.** `PositionManager.on_entry_fill` (satır 121–132) girişte iki algo
emri yerleştiriyor:

```python
pos.active_algos = {pos.sl_id, pos.tp_id}
return [self._algo(pos, "STOP_MARKET", sl, pos.sl_id),
        self._algo(pos, "TAKE_PROFIT_MARKET", tp, pos.tp_id)]
```

`closePosition=true` ile. 105'e ulaşınca **Binance kendi tetikler**, bizim kod bir şey göndermez.

Paper'daki karşılığı: `SimExecutor.on_mark` (`execution/sim.py:88`), yalnızca `markPriceUpdate`
olayında (`trader.py:106`), yani saniyede bir.

- **A) Feature→State→Decision zincirini bekliyor mu:** hayır; o zincir yalnızca bar kapanışında ve
  yalnızca **giriş** için çalışıyor.
- **B) Market event'lerini bağımsız tüketip doğrudan exit üretebiliyor mu:** hayır; çıkış üretimi
  `ctrl/tick` olayına bağlı.

**Ayrı fast-path var mı:** TP **YOK** (borsada). SL için yedek yol var ama tick'e bağlı
(R1, `t_backup_ms=1500`). Trailing **YOK** (tick). Emergency **YOK** (tick, `t_protect_ms=3000`).

---

## 7. Order management

**ExecutionAdapter önünde OMS: KISMEN.** `fbot/core/order_state.py` `OrderBook` sınıfı durum
makinesini içeriyor, ama **yalnızca `TestnetTrader`** kullanıyor (`testnet/main.py:44`,
`self.orders = OrderTracker()`) ve yalnızca `on_user_event` içinde çağrılıyor (satır 93) — o
fonksiyonun da çağıranı yok (§8). Pratikte **çalışmıyor**.

| İstenen durum | Kodda |
|---|---|
| NEW | `OrderStatus.NEW` |
| SENT | **YOK** (istek gönderimi ile ack arası modellenmiyor) |
| ACK | `order_ack` → `OrderStatus.NEW` |
| PARTIALLY_FILLED | `OrderStatus.PARTIALLY_FILLED` |
| FILLED | `OrderStatus.FILLED` |
| CANCELED | `OrderStatus.CANCELED` |
| REJECTED | `OrderStatus.REJECTED` |
| UNKNOWN | Ayrı durum **YOK**; `TestnetAdapter._error_event` (satır 89) `{"kind": "order_unknown", "needs_reconcile": True}` üretiyor, `OrderBook`'ta karşılığı yok |

Ek durumlar: `EXPIRED`, `EXPIRED_IN_MATCH` (STP). Geriye düşme koruması `_RANK` ile (satır 91).
Tekrar bastırma `trade_id` ile (satır 75–80).

**clientOrderId üretimi:**

- Giriş: `decision.decide_explain` satır 93–95, `cid = f"e{sym}{v['bar_end_ms']}{'L'|'S'}"`,
  `[:36]` kırpma. Deterministik, bar sonu zamanına bağlı.
- Koruma: `Position.sl_id` = `f"{pos_id}-SL-v{sl_version}"`, `tp_id` benzeri
  (`position.py:89–94`).
- Çıkış: `PositionManager._exit_order`, `f"{pos_id}-{tag}-v{exit_seq}"`.

**Retry sırasında duplicate engelleniyor mu: YOK.** Kodda retry döngüsü hiç yok.
`TestnetClient.signed` tek deneme yapıyor. `RateLimiter.on_response` geri çekilme **penceresi**
işaretliyor (`rate_limit.py:106`) ama isteği tekrarlamıyor. Deterministik id'ler doğal koruma
sağlıyor ama bu senaryo **test edilmedi**.

---

## 8. Binance private events

**User Data Stream kullanılıyor mu: HAYIR.**

Kanıt: `TestnetClient.listen_key` (`gateway/testnet.py:121`) ve `keepalive_listen_key` (satır 129)
tanımlı, **hiçbir yerden çağrılmıyor**. `fbot/gateway/userdata_map.py` `map_user_event` tanımlı,
**çağıranı yok**. `TestnetTrader.on_user_event` (`testnet/main.py:91`) tanımlı, **çağıranı yok**.
`/private` kategorisi için `CategoryConnection` hiç oluşturulmuyor (`recorder/main.py:194` yalnızca
`("public", "market")`).

| Olay | Kaynak |
|---|---|
| order acknowledgement | REST cevabı (`TestnetAdapter._order` satır 69) |
| partial fill | **YOK** |
| fill | **YOK** (testnet); paper'da `SimExecutor` |
| cancel | REST cevabı (satır 49–52) |
| reject | REST hata kodu (`_error_event`) |
| position update | **YOK** |
| balance update | **YOK** (yalnızca silahlanmada bir kez `client.balance`) |

**Position state tahmini olarak mı değişiyor: EVET, tahmini.** Testnet'te dolum olayı gelmediği
için pozisyon yalnızca REST ack'inden türetiliyor. Paper'da simülatörün ürettiği
`entry_fill`/`exit_fill` olaylarından.

---

## 9. Reconciliation

**Startup mutabakatı: VAR.** `fbot/execution/exchange_state.py`, `fetch_snapshot` +
`ReconcileSupervisor`. `TestnetRecorder.resolve_universe` (`testnet/main.py:125–133`) kurup
`self._reconcile(...)` çağırıyor; `TestnetRecorder._beat` (satır 156) 10 saniyede bir tekrarlıyor.

Kapsam: open orders (`/fapi/v1/openOrders`), open algos (`/fapi/v1/openAlgoOrders`), positions
(`/fapi/v2/positionRisk`), leverage, position mode (`/fapi/v1/positionSide/dual`).
**Balance mutabakatı YOK.**

Karşılaştırma `fbot/core/reconcile.py:reconcile`. Fark bulunursa `state.reconciled = False` →
`risk.assess` K2 (`core/risk.py:96`) her girişi reddediyor.

**WS kopup geri geldiğinde missed fill tespiti: YOK.** User data stream olmadığı için kaçırılacak
fill zaten alınmıyor. Mutabakat 10 saniyelik periyotta pozisyon farkını yakalar; bu fill tespiti
değil, durum farkı tespitidir.

---

## 10. Risk fast path

| Kontrol | Durum | Yer |
|---|---|---|
| stale market data | VAR | `risk.py:99–101` K4, `Engine._staleness` besliyor |
| stale user stream | **YOK** | user stream yok |
| max position | VAR | K6, `risk.py:105` |
| max notional | VAR | K8 `gross_cap_usdt`, `risk.py:111` |
| max daily loss | **YOK** | `RiskConfig`'te alan yok |
| max drawdown | **YOK** | |
| duplicate order | KISMEN | deterministik `clientOrderId`; `state.pending_entries` (`engine.py:237,262`) aynı sembolde ikinci girişi engelliyor. Emir seviyesinde dedupe **YOK** |
| runaway order protection | **YOK (bağlı değil)** | `RunawayDetector` `risk.py:178` tanımlı, hiçbir yerden import/instantiate edilmiyor |
| kill switch | VAR | K1 `risk.py:94`; dosya `gateway/killswitch.py`; `paper_status_task` 10 s'de bir okuyor |
| disconnect protection | KISMEN | bayatlık → `force_reconnect` + K4 + `_apply_freeze` pozisyonları FROZEN yapıyor |
| orphan order protection | VAR | `reconcile.py:55–60` `algo_orphan`; tespit eder, **iptal etmez** |

Ek kontroller: K5 clock skew, K7 sembol meşgul, K9 beta, K10 kaldıraç, K11 teminat, K12 filtreler,
K13 spread, K14 katılım, K15 slippage, K16 cooldown, K17 emir bütçesi, K18 429/418.

---

## 11. Latency instrumentation

| Timestamp | Durum |
|---|---|
| exchange_event_ts | **YOK** canlı yolda. Ham `E` alanı kayıtta duruyor, çıkarılmıyor |
| socket_receive_ts | VAR — `ws_category.py:59`, `recv_ns = time.time_ns()` + `mono_ns` |
| parse_ts | **YOK** |
| dispatch_ts | **YOK** |
| decision_start_ts | **YOK** |
| decision_end_ts | **YOK** |
| risk_end_ts | **YOK** |
| order_send_ts | **YOK** (`_cmd_payload` içindeki `t_ns` `emit` anıdır) |
| order_ack_ts | **YOK** |
| first_fill_ts | **YOK** |
| final_fill_ts | **YOK** |

**ws_lag formülü** (`scripts/latency_core.py:56`):

```python
"lag_E_ms": recv_wall_ms - e_time    # e_time = data["E"]
```

`recv_wall_ms` soketten okuma anındaki duvar saati, `E` Binance'ın olayı ürettiği zaman.

**p99 = 606 ms neyi ölçüyor:** bu **canlı sistemin ölçümü değildir.** `scripts/measure_latency.py`
ile 2026-09-10/11'de 24 saat koşan **ayrı bir process**in `btcusdt@bookTicker` akışında ölçtüğü
`recv_wall_ms − E` dağılımının 99. persentili. İçinde borsa içi gecikme, ağ ve saat kayması vardır.
Konsol bu değeri `docs/latency-baseline.generated.md` dosyasından okur
(`api/server.py:parse_latency_md`), canlı trader'dan değil.

**loop_lag formülü** (`recorder/main.py:155–165`):

```python
t0 = time.monotonic()
await asyncio.sleep(0.1)
self.lag_samples.append((time.monotonic() - t0 - 0.1) * 1000)
```

100 ms uyku isteğinin **fazladan ne kadar sürdüğü**. Event loop doygunluk göstergesidir, emir
gecikmesi değildir. Persentil `latency_core.percentiles`, nearest-rank.

---

## 12. Stale data

**Kaynak:** `config/recorder.toml` → `[staleness_s] public = 30, market = 30`. İki yerde
kullanılıyor:

- `Recorder.staleness_task` (`main.py:136`) — `cfg.staleness_s`, son çerçevenin **monotonic** yaşı
- `Engine._staleness` (`engine.py:305`) — `cfg.staleness_ms`, `state.last_recv_ns[cat]` üzerinden

**Ne stale ilan ediliyor:** kategori. Sembol bazında **değil**. `/market` bağlantısında hiç çerçeve
gelmezse 10 sembolün hepsi birden bayat sayılır.

**30 saniye veri yoksa:**

- Yeni trade: **durur.** `decide_explain` D3 (`decision.py:82`) `v["stale"]` ile, ayrıca K4
  (`risk.py:99`). İki kat koruma.
- Açık pozisyon: **FROZEN.** `Engine._apply_freeze` (`engine.py:155`) `pm.freeze(pos)` çağırıyor.
  `PositionManager.on_tick` satır 173'te `if pos.state != PosState.MANAGED: return []` — yani
  **hiçbir kural çalışmaz**: trailing durur, yedek stop durur, zaman aşımı durur.
- Açık emirler: **dokunulmaz.** Borsadaki SL/TP algo emirleri yerinde kalır ve tetiklenebilir.
- Ayrıca `force_reconnect` çağrılır (`main.py:143`).

---

## 13. Paper / testnet determinism

**Ayrı bağlantı: EVET.** Üç process kendi `CategoryConnection`'ını açıyor. Aynı borsa olayını
**farklı zamanda** alırlar; `recv_ns` damgaları farklıdır.

**Farklı ordering: EVET mümkün.** Sequence her process'te kendi `Sequencer`'ından geliyor. İki ayrı
TCP bağlantısında public ve market çerçevelerinin göreli sırası ağ koşullarına bağlıdır; iki
process'te farklı sıralanabilir.

**Ortak canonical stream modu: KISMEN.** `fbot/replay/harness.py:replay` ve `scripts/replay.py`
kaydedilmiş akışı oynatıyor, `ReplayClock` ile; `scripts/replay_positions.py` pozisyon
simülasyonunu da yapıyor. Ama bu **offline replay**'dir; `PaperRecorder`/`TestnetRecorder`'ı
kayıtlı akışla besleyen bir çalışma modu **YOK**.

---

## 14. Execution transport

**REST.** `TestnetAdapter → TestnetClient.signed → _http` (`gateway/testnet.py:34`).

- **Persistent connection: YOK.** Her istek `http.client.HTTPSConnection(_HOST, timeout=timeout)`
  açıp `finally: conn.close()` ile kapatıyor. Her emirde yeni TCP + TLS el sıkışması.
- **Connection pooling: YOK.**
- **Timeout:** `TestnetClient.timeout = 10.0` saniye (satır 50); bağlanma ve okuma ayrı değil.
- **Retry politikası: YOK.** Tek deneme. `RateLimiter` geri çekilme penceresi işaretliyor, isteği
  tekrarlamıyor.

**WebSocket API: YOK.** Kilitli kararda "WebSocket API + Ed25519" yazıyor; implementasyon REST.

**Başka transport eklenebilir mi: EVET.** `TestnetAdapter.submit(cmd, now_ms) -> dict` arayüzü
komut nesnesi alıp olay sözlüğü döndürüyor; `TestnetTrader._send` yalnızca bu sözleşmeye bağlı.
`LiveExecutionAdapter` (`execution/adapter.py:27`) aynı arayüzü korumalı stub olarak taşıyor.

---

## 15. CPU / runtime

- **Event loop:** CPython varsayılan `asyncio`. uvloop **YOK**.
- **CPU-bound bölüm: VAR.** Her olayda `json.loads` iki kez (`stream_of` ve `Engine.step`). Bar
  kapanışında `compute_features` + `rolling_pct` saf Python döngüleri, `Decimal` aritmetiği. Tek
  thread olduğu için bu iş WS okuma döngüsünü bloke ediyor.
- **Blocking I/O: VAR.** SQLite yazımı `_step` içinde; testnet REST çağrıları `to_thread` olmadan.
- **CPU affinity / pinning: YOK.**
- **Container limitleri:** `fbot-paper` ve `fbot-testnet` için `mem_limit: 1g`, `cpus: 1.0`.
  **`fbot-recorder` için limit YOK.**
- **GC pause ölçümü: YOK.** Kodda `gc` modülü hiç kullanılmıyor.

---

## 16. Özet tablo

| Alan | Durum | Risk | Hot-path etkisi | Öneri |
|---|---|---|---|---|
| Pozisyon yönetimi tetikleme | tick'e bağlı, 1000 ms | **Yüksek** | Uygulama tarafı çıkışlar ≤1 s gecikir | Market olayında `_tick_positions` çağır ya da ayrı fast-path |
| TP/SL tetikleme | yalnızca borsada | Orta | Uygulama tarafı yedeği yok | Uygulama tarafı TP kontrolü ekle (R1'in TP karşılığı) |
| User data stream | **YOK** | **Yüksek** | Fill/partial/reject görülmüyor | `listen_key` + `/private` bağlantısı + `map_user_event` bağla |
| OMS | yazıldı, bağlı değil | **Yüksek** | Emir durumu takip edilmiyor | User stream ile birlikte devreye al |
| SQLite hot path'te | her olayda insert | Orta | WS döngüsünü bloke eder | Yazımı kuyruğa al, `writer_task` gibi |
| REST bağlantı yeniden kurulumu | her emirde TLS | Orta | Emir başına yüzlerce ms | Persistent session / connection pool |
| Retry politikası | **YOK** | Orta | Geçici hata = kayıp emir | İdempotent retry, deterministik id ile |
| Head-of-line blocking | shard yok | Orta | Burst'te tüm semboller bekler | Sembol shard'ı veya kuyruk ayrımı |
| Latency ölçümü | yalnızca `recv_ns` | Orta | Darboğaz görünmüyor | Karar ve emir damgalarını ekle |
| Runaway koruması | yazıldı, bağlı değil | Orta | Kaçak emir üretimi durmaz | `RunawayDetector`'ı trader'a bağla |
| Daily loss / drawdown | **YOK** | Orta | Gün içi kayıp sınırsız | `RiskConfig`'e ekle |
| Bayatlıkta açık emir | dokunulmuyor | Orta | Bağlantı yokken borsa emri tetiklenebilir | Bilinçli tercih, dokümante et |
| Sembol bazlı bayatlık | kategori bazlı | Düşük | Tek sembol sorunu hepsini etkiler | Sembol bazlı yaş takibi |
| Balance mutabakatı | **YOK** | Düşük | Teminat sapması görülmez | `fetch_snapshot`'a ekle |
| Ortak canonical stream | offline replay var | Düşük | Paper/testnet aynı akışta koşamaz | Replay-besleme modu |

---

## Hedef sorusunun cevabı

> "Market analiz motoru başka bir event'i işlerken açık pozisyon +%5 TP seviyesine ulaşırsa,
> mevcut kod SELL order intent'i gecikmeden bağımsız olarak üretebilir mi?"

### KISMEN

**Borsa tarafı çalışır.** `PositionManager.on_entry_fill`, `core/position.py:131–132`:

```python
pos.active_algos = {pos.sl_id, pos.tp_id}
return [self._algo(pos, "STOP_MARKET", sl, pos.sl_id),
        self._algo(pos, "TAKE_PROFIT_MARKET", tp, pos.tp_id)]
```

`_algo` `close_position=True` ile gönderiyor. Bot hiçbir şey yapmasa bile Binance tetikler. Bu
yüzden cevap "hayır" değil.

**Uygulama tarafı üretmez.** `Engine.step`, `core/engine.py:82–86` — `_tick_positions` yalnızca
`ev.stream == "tick"` dalında. Market olayları satır 89–99'da yalnızca `_route` çağırıyor, `_route`
satır 188–196'da `aggTrade` için yalnızca `m.on_agg_trade(d)` yapıyor.

**Tick gelse bile TP yok.** `PositionManager.on_tick`, `core/position.py:166–224` — `tp_price` hiç
okunmuyor. Kurallar: koruma zaman aşımı, R2 `degrade_map`, R1 `sl_price` geçilmesi, R5
`max_hold_ms`, R4 `tp1_pct`, R3 `lock_trigger_pct`. TP kontrolü **YOK**.

**Gecikme kaynağı.** `Recorder.tick_task`, `recorder/main.py:151` —
`await asyncio.sleep(self.cfg.tick_ms / 1000)`, config'te 1000 ms. Uygulama tarafı her çıkış kuralı
en kötü durumda 1 saniye bekler.

---

## Event-flow diyagramı

```
                        Binance USDⓈ-M
                    ┌──────────┴──────────┐
             wss /public              wss /market
        bookTicker, depth@100ms   aggTrade, markPrice@1s, forceOrder
                    │                     │
                    └──────────┬──────────┘
                   CategoryConnection.run          ws_category.py:58
                   recv_ns=time_ns(), mono_ns              :59
                               │ senkron çağrı
                        on_frame(raw,...)           recorder/main.py:94
                               │
                        stream_of(raw)  [json #1]      events.py:50
                               │
                     ┌─── Recorder.emit ───┐          recorder/main.py:76
                     │                     │
            Sequencer.next            queue.put_nowait
            (GLOBAL seq)              asyncio.Queue(500k)
                     │                     │  dolarsa: dropped++
                     │               writer_task → RotatingGzipWriter
                     │                          (gzip, hot path DIŞI)
                     │
            PaperTrader.on_event                  paper/trader.py:52
                     │
            ┌────────┴────────┐
            │                 │
      _step → Engine.step   _feed_sim_from / _drain_sim
            │                 └─ markPriceUpdate → SimExecutor.on_mark
            │                       (paper'da algo tetikleme, ~1 Hz)
            │
     ┌──────┴───────────────────────────────┐
     │ ev.cat == "ctrl" and stream=="tick"  │   ← SADECE BURADA
     │   → _staleness                       │
     │   → _apply_freeze                    │
     │   → _tick_positions ──► PositionManager.on_tick
     │        (R1 yedek stop, R2 bozulma,   │      TP YOK
     │         R3 trail, R4 kısmi, R5 süre) │      1000 ms periyot
     └──────────────────────────────────────┘
            │
     ┌──────┴──────────────────────────────┐
     │ market olayı (aggTrade/bookTicker/  │
     │ markPrice)                          │
     │   → json.loads [json #2]            │
     │   → _route                          │
     │       aggTrade → SymbolMarket.on_agg_trade
     │           └─ bar kapandıysa:
     │                _on_bar_state
     │                  ├─ SymbolStateEngine.on_bar_cmds
     │                  ├─ BetaTracker.on_bar
     │                  └─ _decide
     │                       ├─ decide_explain  D1∧D2∧D3
     │                       ├─ assess          K1–K18
     │                       └─ PlaceOrder
     │       bookTicker → m.on_book_ticker   (yalnızca fiyat)
     │       markPrice  → m.on_mark_price + funding tahakkuk
     │       depth/forceOrder → [] (görünüme dahil değil)
     │   → _staleness → _apply_freeze (FROZEN/unfreeze)
     └─────────────────────────────────────┘
            │
      komut döngüsü                          paper/trader.py:74-88
            ├─ emit("ctrl","command")  → kayda
            ├─ store.record_order  (SQLite, HOT PATH İÇİNDE)
            └─ adapter.submit
                  ├─ paper : SimExecutor.submit  (bellek)
                  └─ testnet: TestnetAdapter.submit
                        → TestnetClient.place_order / place_algo
                        → RateLimiter.allow_order
                        → _http: yeni HTTPSConnection (TLS her seferinde)
                        → SENKRON, event loop BLOKE
                        → dönüş: order_ack | order_rejected | order_unknown

      ╔══════════════════════════════════════════════════╗
      ║ wss /private  → YOK                              ║
      ║ listen_key()  → tanımlı, çağrılmıyor             ║
      ║ map_user_event → tanımlı, çağrılmıyor            ║
      ║ OrderBook (OMS) → tanımlı, beslenmiyor           ║
      ║ Sonuç: fill / partial / reject görülmüyor        ║
      ╚══════════════════════════════════════════════════╝

      10 s periyot:  ReconcileSupervisor.check
                       → fetch_snapshot (4 imzalı REST)
                       → reconcile → state.reconciled
                       → fark varsa K2 tüm girişleri reddeder
```
