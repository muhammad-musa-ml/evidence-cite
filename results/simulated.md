seeds [1, 2, 3, 4, 5], 400 samples per seed (1600 findings per seed and noise level), fault rates {'fabricated': 0.02, 'wrong_page': 0.02, 'value_drift': 0.02, 'wrong_line': 0.02, 'verdict_flip': 0.02}, silent repair 0.5

Each cell is the mean over seeds, then (min-max) over seeds, in percent.

| noise | checker | verified | weak | rejected | clean findings rejected | faulty findings verified | wrong verdicts verified (share of all findings) |
|---|---|---|---|---|---|---|---|
| 0% | trust | 100.0 (100.0-100.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 100.0 (100.0-100.0) | 4.9 (4.4-5.4) |
| 0% | exact | 91.7 (90.6-92.1) | 0.0 (0.0-0.0) | 8.3 (7.9-9.4) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) |
| 0% | tiered | 91.7 (90.6-92.1) | 0.0 (0.0-0.0) | 8.3 (7.9-9.4) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) |
| 2% | trust | 100.0 (100.0-100.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 100.0 (100.0-100.0) | 5.8 (5.3-6.1) |
| 2% | exact | 73.1 (70.8-74.9) | 0.0 (0.0-0.0) | 26.9 (25.1-29.2) | 20.3 (18.7-22.9) | 0.1 (0.0-0.7) | 0.8 (0.6-1.1) |
| 2% | tiered | 72.3 (70.1-74.1) | 19.4 (18.1-21.8) | 8.3 (7.9-9.3) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) |
| 5% | trust | 100.0 (100.0-100.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 100.0 (100.0-100.0) | 7.2 (6.9-7.6) |
| 5% | exact | 52.1 (51.2-52.8) | 0.0 (0.0-0.0) | 47.9 (47.2-48.8) | 43.2 (42.6-44.2) | 0.9 (0.0-2.3) | 1.9 (1.4-2.2) |
| 5% | tiered | 50.2 (49.5-50.8) | 41.5 (40.9-42.5) | 8.2 (7.8-9.3) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) |

Per injected fault, tiered checker, at 5% noise, seeds pooled (counts of findings; the same faults are injected at every noise level):

| fault | injected | verified | weak | rejected |
|---|---|---|---|---|
| fabricated | 148 | 0 | 0 | 148 |
| wrong_page | 110 | 0 | 0 | 110 |
| value_drift | 171 | 0 | 0 | 171 |
| wrong_line | 70 | 0 | 0 | 70 |
| verdict_flip | 166 | 0 | 7 | 159 |
