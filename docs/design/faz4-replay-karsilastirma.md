# Faz 4 replay karşılaştırması — `rec-72h` (SL 0.5%, TP 1.0%, W=120, giriş S1 long / S2 short, 80 USDT, taker/taker)

Kârlılık gösterilmedi (ADR 0010). Bilgilendirici karşılaştırma (ADR 0011).

| ölçüt | statik SL/TP | statik + R1/R3/R5 |
|---|---|---|
| positions | 7 | 11 |
| open_at_end | 8 | 7 |
| net_mean_pct | -0.4263033577100226 | -0.1963774522213187 |
| net_sum_pct | -2.9841235039701584 | -2.160151974434506 |
| win_rate | 0.14285714285714285 | 0.45454545454545453 |
| was_profit | 4 | 7 |
| profit_to_loss_rate | 0.75 | 0.2857142857142857 |
| replacements | 0 | 10 |
| exit_reasons | {'sl': 6, 'tp': 1} | {'sl': 10, 'tp': 1} |
| commands | {'BarClosed': 1760, 'PlaceAlgo': 30, 'CancelAlgo': 7} | {'BarClosed': 1760, 'PlaceAlgo': 46, 'CancelAlgo': 21} |
| synthetic_ticks | True | True |
