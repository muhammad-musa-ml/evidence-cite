from __future__ import annotations

import argparse
import hashlib
import json
import random
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Callable

from .attributes import ATTRIBUTES, CLAIMS
from .evaluate import cell
from .models import Citation, Claim, Finding
from .synth import Sample, add_noise, make_population
from .verify import verify

CHECKERS = ("trust", "exact", "tiered")
TEMPERATURE = 0

RULES = {
    "amount_match": "pass if po_total and invoice_total are equal, otherwise exception",
    "invoice_after_po": "pass if the invoice date is on or after the PO date, otherwise exception",
    "approval_within_limit": "pass if approver_limit is at least po_total, otherwise exception",
    "vendor_match": "pass if po_vendor and invoice_vendor are the same vendor, otherwise exception",
}


def build_prompt(sample: Sample) -> str:
    docs = "\n\n".join(
        f"Document {d.doc_id}, page {i}:\n{page}" for d in sample.docs for i, page in enumerate(d.pages, 1)
    )
    attributes = "\n".join(
        f"- {name} (claims: {', '.join(rule.claims)}): {RULES[name]}" for name, rule in ATTRIBUTES.items()
    )
    claims = "\n".join(
        f"- {name}: the line labelled \"{label.capitalize()}\" in the {kind} document"
        for name, (kind, label) in CLAIMS.items()
    )
    return (
        "You are testing one purchase for an internal audit. The text below comes from OCR.\n\n"
        f"{docs}\n\n"
        f"Attributes to test:\n{attributes}\n\n"
        f"Where each claim comes from:\n{claims}\n\n"
        "Return only JSON of the form "
        '{"findings": [{"attribute": "...", "verdict": "pass or exception", "claims": '
        '[{"name": "...", "value": "...", "doc_id": "...", "page": 1, "quote": "..."}]}]}. '
        "One finding per attribute. For each claim, quote the whole line exactly as it appears "
        "in the document and give the value from that line. doc_id is the document id alone, "
        f"for example {sample.sample_id}/po, and page is the page number."
    )


def ask_ollama(model: str, prompt: str, url: str = "http://localhost:11434", timeout: int = 600) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": TEMPERATURE, "num_ctx": 4096},
    }).encode()
    req = urllib.request.Request(f"{url}/api/chat", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)["message"]["content"]


def parse(content: str, sample: Sample) -> dict[str, Finding]:
    """The findings in a model reply, by attribute. Anything malformed is simply absent."""
    try:
        data = json.loads(content)
        entries = data["findings"]
    except (ValueError, KeyError, TypeError):
        return {}
    out: dict[str, Finding] = {}
    for e in entries if isinstance(entries, list) else []:
        try:
            claims = tuple(
                Claim(str(c["name"]), str(c["value"]), Citation(str(c["doc_id"]), int(c["page"]), str(c["quote"])))
                for c in e["claims"]
            )
            finding = Finding(sample.sample_id, str(e["attribute"]), claims, str(e["verdict"]).lower())
        except (KeyError, TypeError, ValueError):
            continue
        out.setdefault(finding.attribute, finding)  # a second finding for an attribute is ignored
    return out


def shown_population(seed: int, n: int, noise: float) -> list[Sample]:
    """The samples as the model sees them. run() and score() both build them here, so they cannot differ."""
    noise_rng = random.Random(f"noise-{seed}-{noise}")  # drawn in sample order
    return [add_noise(sample, noise, noise_rng) for sample in make_population(seed, n)]


def run(model, seeds, n, noises, ask: Callable[[str], str], log=print, on_record=None) -> list[dict]:
    """Ask the model about every sample; the raw replies are the record."""
    records = []
    for seed in seeds:
        for noise in noises:
            for shown in shown_population(seed, n, noise):
                try:
                    content, error = ask(build_prompt(shown)), None
                except Exception as exc:  # a failed call is a result, not a crash
                    content, error = "", f"{type(exc).__name__}: {exc}"
                records.append({"model": model, "temperature": TEMPERATURE, "seed": seed, "noise": noise,
                                "sample_id": shown.sample_id, "content": content, "error": error})
                if on_record:
                    on_record(records[-1])
                log(f"seed {seed} noise {noise} {shown.sample_id} {'error' if error else 'ok'}")
    return records


def score(records: list[dict]) -> dict:
    """(noise, checker) -> one Counter per seed, from stored replies alone."""
    conditions: dict = {}
    for rec in records:
        conditions.setdefault((rec["seed"], rec["noise"]), []).append(rec)
    results: dict = {}
    for (seed, noise), recs in sorted(conditions.items()):
        n = max(int(r["sample_id"][1:]) for r in recs)  # the draws for the first n samples do not depend on more
        shown = {s.sample_id: s for s in shown_population(seed, n, noise)}
        counters = {c: Counter() for c in CHECKERS}
        for rec in recs:
            sample = shown[rec["sample_id"]]
            found = parse(rec["content"], sample)
            for attribute in ATTRIBUTES:
                finding = found.get(attribute)
                for checker in CHECKERS:
                    c = counters[checker]
                    c["expected"] += 1
                    if finding is None:
                        c["missing"] += 1
                        continue
                    result = None if checker == "trust" else verify(finding, sample.corpus(), checker)
                    status = "verified" if result is None else result.status
                    right = "right" if finding.verdict == sample.truth[attribute] else "wrong"
                    c["findings"] += 1
                    c[status] += 1
                    c[right] += 1
                    c[f"{status}_{right}"] += 1
                    if checker == "tiered" and status != "verified":
                        for reason in {r.split(": ")[-1] for r in result.reasons}:
                            c[f"reason:{reason}"] += 1
        for checker in CHECKERS:
            results.setdefault((noise, checker), []).append(counters[checker])
    return results


def pages_digest(records: list[dict]) -> str:
    """sha256 over the prompt (so the pages) of every sample the replies were collected on, in file order."""
    h = hashlib.sha256()
    shown: dict = {}
    for rec in records:
        key = (rec["seed"], rec["noise"])
        if key not in shown:
            n = max(int(r["sample_id"][1:]) for r in records if (r["seed"], r["noise"]) == key)
            shown[key] = {s.sample_id: s for s in shown_population(rec["seed"], n, rec["noise"])}
        h.update(build_prompt(shown[key][rec["sample_id"]]).encode("utf-8"))
        h.update(b"\0")
    return h.hexdigest()


def describe(records: list[dict]) -> dict:
    """What the replies themselves say about the run; a field they do not carry is left empty."""
    per_condition = Counter((r["seed"], r["noise"]) for r in records)
    return {
        "models": sorted({r["model"] for r in records if "model" in r}),
        "temperatures": sorted({r["temperature"] for r in records if "temperature" in r}),
        "seeds": sorted({r["seed"] for r in records}),
        "samples": sorted(set(per_condition.values())),
    }


def render(results: dict, meta: dict) -> str:
    noises = sorted({k[0] for k in results})
    models = ", ".join(meta["models"]) or "not recorded in the replies"
    temps = ", ".join(map(str, meta["temperatures"])) or "not recorded in the replies"
    out = [
        f"model {models}, seeds {meta['seeds']}, samples per seed and noise level "
        f"{meta['samples']}, temperature {temps}",
        "",
        "Findings are the four attributes per sample that the model returned in a parseable form.",
        "Each cell is the mean over seeds, then (min-max) over seeds, in percent.",
        "",
        "| noise | checker | findings returned | verdict wrong | verified | weak | rejected "
        "| wrong verdict marked verified | right verdict rejected |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for noise in noises:
        for checker in CHECKERS:
            cs = results[(noise, checker)]
            out.append(
                f"| {noise * 100:g}% | {checker} | {cell(cs, 'findings', 'expected')} "
                f"| {cell(cs, 'wrong', 'findings')} | {cell(cs, 'verified', 'findings')} "
                f"| {cell(cs, 'weak', 'findings')} | {cell(cs, 'rejected', 'findings')} "
                f"| {sum(c['verified_wrong'] for c in cs)} of {sum(c['findings'] for c in cs)} "
                f"| {sum(c['rejected_right'] for c in cs)} of {sum(c['findings'] for c in cs)} |"
            )
    out += ["", "Why the tiered checker did not mark a finding verified (findings, pooled over seeds; "
            "a finding can have several reasons):", "",
            "| noise | reason | findings |", "|---|---|---|"]
    for noise in noises:
        reasons: Counter = Counter()
        for c in results[(noise, "tiered")]:
            for key, val in c.items():
                if key.startswith("reason:"):
                    reasons[key[7:]] += val
        for reason, count in sorted(reasons.items(), key=lambda kv: (-kv[1], kv[0])):
            out.append(f"| {noise * 100:g}% | {reason} | {count} |")
    return "\n".join(out) + "\n"


def main(argv=None, ask: Callable[[str], str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Use a local model as the extractor and score its findings.")
    ap.add_argument("--model", default="qwen3:4b-instruct-2507-q4_K_M")
    ap.add_argument("--url", default="http://localhost:11434")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--n", type=int, default=20, help="samples per seed and noise level")
    ap.add_argument("--noise", default="0,0.05")
    ap.add_argument("--raw", required=True, help="JSON Lines file of the model's replies (written, or read with --replay)")
    ap.add_argument("--replay", action="store_true", help="score the replies in --raw without calling the model")
    ap.add_argument("--expect-digest", help="with --replay: stop unless the prompts the replies were collected on hash to this")
    ap.add_argument("--out", help="also write the table to this file")
    args = ap.parse_args(argv)

    raw = Path(args.raw)
    if args.replay:
        records = [json.loads(line) for line in raw.read_text(encoding="utf-8").splitlines() if line]
        if args.expect_digest and pages_digest(records) != args.expect_digest:
            raise SystemExit("the prompts built from the generated pages differ from the ones these replies were collected on")
    else:
        seeds = range(1, args.seeds + 1)
        noises = [float(x) for x in args.noise.split(",")]
        ask = ask or (lambda prompt: ask_ollama(args.model, prompt, args.url))
        with raw.open("w", encoding="utf-8", newline="\n") as f:
            def keep(record):
                f.write(json.dumps(record) + "\n")
                f.flush()  # a stopped run keeps what it has

            records = run(args.model, seeds, args.n, noises, ask, on_record=keep)
    text = render(score(records), describe(records))
    print(text, end="")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
