# evidence-cite

A checker for the findings a model reports from scanned documents. A finding counts as verified only when every value it rests on is on the page and line it cites, and its verdict follows from those values. I wrote it to try out a promise on Oxus's site: each result links to the exact document, page and value it relied on.

## The task

A purchase three-way match. A sample is a purchase order (one page), an invoice (two pages) and an approval record (one page), as page text. Four attributes are tested per sample: the invoice total equals the order total, the invoice is not dated before the order, the approver's limit covers the order, and the invoice vendor is the order vendor. For each attribute the extractor returns a verdict (pass or exception) and two claims. A claim is a value with a citation: document id, page number and the line it quotes.

## What the checker does

For each claim it checks that:

1. the cited document exists, belongs to the same sample and is the kind the claim needs (the order total comes from the purchase order);
2. the cited page exists;
3. the quote is one whole line of that page, compared after case, whitespace and Unicode are normalised, so a quote that cuts a number short or joins two lines is rejected;
4. the line starts with the label the claim needs (`Total due:` for the invoice total);
5. what follows the label is the claimed value, compared the same way, so a sign, a bracket or a longer name does not pass.

Then it recomputes the verdict from the claimed values, and the reported verdict has to match it. In tiered mode it matches if either reading of the look-alikes gives the reported verdict.

A finding comes out verified, weak or rejected. Weak means a person should look: a claim matched only after OCR look-alikes were folded back (O and o to 0; L, l, I, i and | to 1; S and s to 5; B and b to 8; Z and z to 2), another line of the page has the same label and a different value, or, in tiered mode, the verdict differs between the two readings or exists only once the look-alikes are folded (a value that does not parse as written). `exact` mode never folds. `tiered` mode, the default, tries exact first and then folds. A rejected claim comes with its reason, and a claim that stands comes with its span in the original page, for highlighting.

## Run it

```
python -m unittest discover
python -m evidence_cite.evaluate --out results/simulated.md
python -m evidence_cite.llm --raw results/qwen3-4b-raw.jsonl --replay --out results/qwen3-4b.md
python -m evidence_cite.llm --raw new.jsonl --out new.md
```

Standard library only, 138 tests; I ran it on Python 3.13. The last command asks a local Ollama model again (Ollama on localhost with the model pulled; `--model`, `--url`, `--seeds`, `--n` and `--noise` change the run). On a replay, `--expect-digest <sha256>` stops the run if the prompts the code now builds (the pages plus the instructions) are not the ones the replies were collected on; the digest of the stored run is the `pages-sha256` line of `results/qwen3-4b-run.txt`, and a test checks it too.

## Simulated extractor

`results/simulated.md` is the output of the second command: 5 seeds of 400 samples, 1,600 findings per seed and noise level. The extractor (`simulate.py`) is a stand-in I wrote. For each finding it draws at most one of five mistakes, 2% each: a quote and value that are not on the page, the right quote cited on another page, one character of the value changed, a real line that is not the labelled one (the unit price instead of the order total, the subtotal instead of the total due), and a flipped verdict. A draw that cannot apply is skipped (a one-page document has no other page to cite, and only the order total and the total due have a real decoy line), so 665 of the 8,000 findings (8.3%) end up faulty. For each claim on a noisy page it copies the noisy line or quotes the clean one, with equal odds, as an extractor that repaired the scan would. Cells are the mean over seeds, then the min and max.

- `trust`, which accepts every finding as given, verifies every faulty finding. Findings with a wrong verdict that it passes are 4.9% (4.4-5.4) of all findings at 0% noise and 7.2% (6.9-7.6) at 5%.
- At 0% noise `exact` and `tiered` verify no faulty finding and reject no clean one.
- At 5% noise `exact` rejects 43.2% (42.6-44.2) of the findings that had no fault, because `exact` needs the quote to match the noisy page letter for letter: a quote the extractor repaired does not, and one it copied fails when a swap lands in the label or turns a digit of the value into a letter. It also verifies 0.9% (0.0-2.3) of the faulty ones: 6 findings over the 5 seeds, all flipped verdicts on vendor names that differ only by look-alikes.
- `tiered` verifies no faulty finding and rejects no clean one at any noise level. At 5% noise it sets 41.5% (40.9-42.5) of all findings aside as weak. Of the 665 faulty findings it rejects 658 and marks 7 weak, all flipped verdicts.

That is a result about the design choice, not about real extractors: the faults are the ones I wrote the checks for.

## A real model

`results/qwen3-4b.md` scores a small local model as the extractor: `qwen3:4b-instruct-2507-q4_K_M` on Ollama, temperature 0, JSON output, one prompt (`build_prompt`). I ran 3 seeds of 20 purchases, each shown clean and with 5% noise: 120 replies over 60 purchases, 480 findings. The replies are in `results/qwen3-4b-raw.jsonl`. The table is rebuilt from that file and the seeds, without the model: `synth.py` regenerates the pages and the true verdicts. The replies do not carry the model or the temperature, so the table header says so; `results/qwen3-4b-run.txt` records them, with the date and the digest of the prompts. I reworded the prompt once, after a one-sample trial in which the model wrote `S0001/po page 1` as the document id. That reply was not kept.

The true verdict is the one the generator planted; the clean pages encode it.

- The model's verdict was wrong on 90 of 240 findings at 0% noise and on 126 of 240 at 5%, 216 of 480 in all. Taking the model at its word passes all 216.
- `tiered` marked none of those 216 verified. `exact` marked 7 of them verified, all at 5% noise: vendor findings whose two names differ only by look-alikes (`Corvin ElectricaI` and `Corvin E1ectrical`), so the verdict does follow from the page as printed.
- Most findings `tiered` did not verify have a verdict that does not follow from the cited values: 74 at 0% noise and 102 at 5%.
- At 0% noise the other 25 are citation mistakes: 20 findings cite a document id that does not exist, 2 a quote that is not on the page, 2 a quote that is not a whole line and 1 a value that is not in its quote. At 5% noise 20 are citation mistakes (13 with a document id that does not exist, 4 with a quote that is not a whole line, 2 that cite page 1 for a quote that is on page 2 and 1 with a value that is not in its quote) and 45 are weak, below.
- Across both noise levels 33 claims cite a document id that does not exist, 31 of them `S0`, all in the invoice-date test. At 5% noise 51 of 240 findings carry an amount or date that does not parse. In 50 of them a value contains a letter (55 claims in all), and for 53 of those 55 that text is on a page of the cited document (the other 2 cite `S0`), so the model copied the OCR error (`5,648.1B`). The other finding has an amount cut short to `4,944.0` (the page says `4,944.00`), which also appears at 0% noise.
- `tiered` rejected 13 findings whose verdict was right, 9 of 240 at 0% noise and 4 of 240 at 5%, because their citation failed. `exact` rejected 41 of 240 at 5%.
- At 5% noise `tiered` sets 18.8% (17.5-20.0) of the findings aside as weak: 45 findings, 30 of them with a claim that matched only after the fold and 18 whose verdict differs between the two readings or exists only once the look-alikes are folded (a finding can have both).

## What this does not show

- The documents come from one generated template, one labelled value per line. Real audit evidence is scanned, tabular and long, and would need line recovery before this check applies.
- The noise only swaps characters of the kinds the fold undoes. A real OCR step also drops and merges text.
- The model run is one small model, one prompt, 60 purchases and 3 seeds. Its verdict accuracy says nothing about larger models, and apart from the one rewording the prompt was not tuned.
- Each prompt got one temperature-0 reply. The seeds change the purchases, not the model's sampling, so a new run need not reproduce the stored replies; only the digest guards what they were collected on.
- At 5% noise some verdicts counted wrong follow from values the noisy page really shows, like the vendor names above. The true verdict is the planted one.
- The checker reads the OCR text, never the scan. A digit the OCR read as a different digit is on the page as printed, so the checker verifies it.
- The checker shows that a value is on the cited line and that the verdict follows from the values. It does not show that the labelled line is the right evidence for the control being tested.
- A verdict that depends on how a look-alike letter is read is reported weak. The checker does not decide which reading is right.
