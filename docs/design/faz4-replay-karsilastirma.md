# Faz 4 replay karşılaştırması — `rec-72h` (SL 0.5%, TP 1.0%, W=120, giriş S1 long / S2 short, 80 USDT, taker/taker)

Kârlılık gösterilmedi (ADR 0010). Bilgilendirici karşılaştırma (ADR 0011).

| ölçüt | statik SL/TP | statik + R1/R3/R5 |
|---|---|---|
| positions | 87 | 143 |
| open_at_end | 9 | 7 |
| net_mean_pct | -0.2450436581243723 | -0.18742070231098248 |
| net_sum_pct | -21.31879825682039 | -26.801160430470492 |
| win_rate | 0.2413793103448276 | 0.36363636363636365 |
| was_profit | 63 | 93 |
| profit_to_loss_rate | 0.6666666666666666 | 0.44086021505376344 |
| replacements | 0 | 140 |
| exit_reasons | {'tp': 21, 'sl': 66} | {'timeout': 11, 'sl': 121, 'tp': 11} |
| commands | {'BarClosed': 4760, 'PlaceAlgo': 192, 'CancelAlgo': 87} | {'BarClosed': 5110, 'PlaceAlgo': 440, 'CancelAlgo': 294, 'PlaceOrder': 11} |
| synthetic_ticks | False | False |
