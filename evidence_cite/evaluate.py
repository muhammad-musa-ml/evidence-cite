from __future__ import annotations

import argparse
import random
from collections import Counter
from pathlib import Path

from .simulate import FAULTS, Produced, extract
from .synth import add_noise, make_population
from .verify import verify

CHECKERS = ("trust", "exact", "tiered")
STATUSES = ("verified", "weak", "rejected")


def judge(checker: str, produced: Produced, corpus: dict) -> str:
    """What a checker does with one finding. `trust` accepts everything as given."""
    if checker == "trust":
        return "verified"
    return verify(produced.finding, corpus, checker).status


def tally(checker: str, items: list) -> Counter:
    c: Counter = Counter()
    for produced, corpus in items:
        status = judge(checker, produced, corpus)
        c["findings"] += 1
        c[status] += 1
        if produced.fault:
            c["faulty"] += 1
            c["faulty_verified"] += status == "verified"
            c[f"fault:{produced.fault}"] += 1
            c[f"fault:{produced.fault}:{status}"] += 1
        else:
            c["clean"] += 1
            c["clean_rejected"] += status == "rejected"
            c["clean_weak"] += status == "weak"
        if status == "verified" and produced.finding.verdict != produced.truth:
            c["wrong_verified"] += 1
    return c


def evaluate(seeds, n, noises, rates, silent_fix):
    """(noise, checker) -> one Counter per seed."""
    results: dict = {}
    for seed in seeds:
        population = make_population(seed, n)
        for noise in noises:
            noise_rng = random.Random(f"noise-{seed}-{noise}")
            extract_rng = random.Random(f"extract-{seed}")  # same draws at every noise level
            items = []
            for sample in population:
                shown = add_noise(sample, noise, noise_rng)
                items.extend((p, shown.corpus()) for p in extract(shown, extract_rng, rates, silent_fix))
            for checker in CHECKERS:
                results.setdefault((noise, checker), []).append(tally(checker, items))
    return results


def cell(counters: list, num: str, den: str) -> str:
    """Mean share over seeds, then (min-max); n/a when no seed has anything in the denominator."""
    shares = [100.0 * c[num] / c[den] for c in counters if c[den]]
    if not shares:
        return "n/a"
    return f"{sum(shares) / len(shares):.1f} ({min(shares):.1f}-{max(shares):.1f})"


def render(results: dict, seeds, n, noises, rates, silent_fix) -> str:
    any_run = next(iter(results.values()))
    per_seed = any_run[0]["findings"]
    out = [
        f"seeds {list(seeds)}, {n} samples per seed ({per_seed} findings per seed and noise level), "
        f"fault rates {rates}, silent repair {silent_fix}",
        "",
        "Each cell is the mean over seeds, then (min-max) over seeds, in percent.",
        "",
        "| noise | checker | verified | weak | rejected | clean findings rejected "
        "| faulty findings verified | wrong verdicts verified (share of all findings) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for noise in noises:
        for checker in CHECKERS:
            cs = results[(noise, checker)]
            out.append(
                f"| {noise * 100:g}% | {checker} | {cell(cs, 'verified', 'findings')} "
                f"| {cell(cs, 'weak', 'findings')} | {cell(cs, 'rejected', 'findings')} "
                f"| {cell(cs, 'clean_rejected', 'clean')} | {cell(cs, 'faulty_verified', 'faulty')} "
                f"| {cell(cs, 'wrong_verified', 'findings')} |"
            )
    last = max(noises)
    out += [
        "",
        f"Per injected fault, tiered checker, at {last * 100:g}% noise, seeds pooled (counts of findings; "
        "the same faults are injected at every noise level):",
        "",
        "| fault | injected | verified | weak | rejected |",
        "|---|---|---|---|---|",
    ]
    for fault in FAULTS:
        cs = results[(last, "tiered")]
        total = sum(c[f"fault:{fault}"] for c in cs)
        parts = [sum(c[f"fault:{fault}:{s}"] for c in cs) for s in STATUSES]
        out.append(f"| {fault} | {total} | {parts[0]} | {parts[1]} | {parts[2]} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Score the checkers on seeded purchase samples.")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--n", type=int, default=400, help="samples per seed, four findings each")
    ap.add_argument("--noise", default="0,0.02,0.05", help="comma list of OCR confusion rates")
    ap.add_argument("--fault-rate", type=float, default=0.02, help="per finding, for each fault type")
    ap.add_argument("--silent-fix", type=float, default=0.5,
                    help="chance an extractor repairs OCR noise in the line it quotes")
    ap.add_argument("--out", help="also write the table to this file")
    args = ap.parse_args(argv)

    seeds = range(1, args.seeds + 1)
    noises = [float(x) for x in args.noise.split(",")]
    rates = {f: args.fault_rate for f in FAULTS}
    results = evaluate(seeds, args.n, noises, rates, args.silent_fix)
    text = render(results, seeds, args.n, noises, rates, args.silent_fix)
    print(text, end="")
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
