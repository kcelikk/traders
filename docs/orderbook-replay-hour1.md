# Order book replay doğrulaması — `rec-72h`

Çözülen olay: 365650 (bookTicker 1/50 örnekli)

| Sembol | snapshot | senkron kuruldu | uygulanan diff | düşülen | tamponlanan | resync (neden) | snapshot karşılaştırma: eşit seviye | local fazla seviye | bookTicker top eşleşme |
|---|---|---|---|---|---|---|---|---|---|
| bnbusdt | 6 | 4 | 22023 | 5492 | 8386 | 2 (gap=2) | 7892/8000 (98.65%, 4 snapshot) | 0 | 57.9% |
| btcusdt | 6 | 5 | 27159 | 5965 | 5965 | 1 (gap=1) | 7876/8000 (98.45%, 4 snapshot) | 8 | 61.7% |
| dogeusdt | 6 | 5 | 23161 | 5090 | 5091 | 1 (gap=1) | 7929/8000 (99.11%, 4 snapshot) | 0 | 74.4% |
| ethusdt | 6 | 5 | 27076 | 5952 | 5950 | 1 (gap=1) | 7921/8000 (99.01%, 4 snapshot) | 1 | 44.1% |
| hypeusdt | 6 | 6 | 29365 | 47 | 48 | 0 (—) | 9688/10000 (96.88%, 5 snapshot) | 2 | 53.3% |
| iostusdt | 6 | 4 | 20047 | 11335 | 11338 | 2 (gap=2) | 5971/6000 (99.52%, 3 snapshot) | 1 | 20.0% |
| nearusdt | 6 | 5 | 21800 | 4712 | 4712 | 1 (gap=1) | 7978/8000 (99.72%, 4 snapshot) | 0 | 75.0% |
| solusdt | 6 | 4 | 20025 | 11308 | 11309 | 2 (gap=2) | 5980/6000 (99.67%, 3 snapshot) | 0 | 70.7% |
| xrpusdt | 6 | 5 | 28626 | 41 | 3169 | 1 (gap=1) | 9862/10000 (98.62%, 5 snapshot) | 0 | 66.9% |
| zecusdt | 6 | 5 | 25795 | 5676 | 5676 | 1 (gap=1) | 7898/8000 (98.72%, 4 snapshot) | 0 | 48.4% |
