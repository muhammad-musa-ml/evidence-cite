model not recorded in the replies, seeds [1, 2, 3], samples per seed and noise level [20], temperature not recorded in the replies

Findings are the four attributes per sample that the model returned in a parseable form.
Each cell is the mean over seeds, then (min-max) over seeds, in percent.

| noise | checker | findings returned | verdict wrong | verified | weak | rejected | wrong verdict marked verified | right verdict rejected |
|---|---|---|---|---|---|---|---|---|
| 0% | trust | 100.0 (100.0-100.0) | 37.5 (36.2-38.8) | 100.0 (100.0-100.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 90 of 240 | 0 of 240 |
| 0% | exact | 100.0 (100.0-100.0) | 37.5 (36.2-38.8) | 58.8 (56.2-61.2) | 0.0 (0.0-0.0) | 41.2 (38.8-43.8) | 0 of 240 | 9 of 240 |
| 0% | tiered | 100.0 (100.0-100.0) | 37.5 (36.2-38.8) | 58.8 (56.2-61.2) | 0.0 (0.0-0.0) | 41.2 (38.8-43.8) | 0 of 240 | 9 of 240 |
| 5% | trust | 100.0 (100.0-100.0) | 52.5 (48.8-56.2) | 100.0 (100.0-100.0) | 0.0 (0.0-0.0) | 0.0 (0.0-0.0) | 126 of 240 | 0 of 240 |
| 5% | exact | 100.0 (100.0-100.0) | 52.5 (48.8-56.2) | 33.3 (28.8-36.2) | 0.0 (0.0-0.0) | 66.7 (63.8-71.2) | 7 of 240 | 41 of 240 |
| 5% | tiered | 100.0 (100.0-100.0) | 52.5 (48.8-56.2) | 30.4 (25.0-35.0) | 18.8 (17.5-20.0) | 50.8 (47.5-55.0) | 0 of 240 | 4 of 240 |

Why the tiered checker did not mark a finding verified (findings, pooled over seeds; a finding can have several reasons):

| noise | reason | findings |
|---|---|---|
| 0% | verdict_mismatch | 74 |
| 0% | no_such_document | 20 |
| 0% | quote_not_on_page | 2 |
| 0% | quote_not_whole_line | 2 |
| 0% | value_not_in_quote | 1 |
| 5% | verdict_mismatch | 102 |
| 5% | ocr_confusion | 30 |
| 5% | verdict_depends_on_ocr_reading | 18 |
| 5% | no_such_document | 13 |
| 5% | quote_not_whole_line | 4 |
| 5% | quote_on_page_2 | 2 |
| 5% | value_not_in_quote | 1 |
