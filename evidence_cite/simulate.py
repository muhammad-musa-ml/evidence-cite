from __future__ import annotations

import random
from dataclasses import dataclass

from .attributes import ATTRIBUTES, parse_claim
from .models import Citation, Claim, Finding
from .synth import Sample

# What a careless extractor gets wrong, one per finding at most:
#   fabricated   a quote and value that are not on the page
#   wrong_page   the right quote cited on another page
#   value_drift  the right quote with one character of the value changed
#   wrong_line   a real line of the right page that is not the labelled one
#   verdict_flip the right claims with the opposite verdict
FAULTS = ("fabricated", "wrong_page", "value_drift", "wrong_line", "verdict_flip")

_SAFE_LETTERS = "acdefghjkmnpqrtuvwxy"  # none of them folds, so a swap is never a look-alike


@dataclass(frozen=True)
class Produced:
    finding: Finding
    fault: str | None  # the fault actually applied
    truth: str  # the true verdict


def perturb(name: str, value: str, rng: random.Random) -> str | None:
    """Change one character so the value still parses but is a different value."""
    spots = [i for i, ch in enumerate(value) if ch.isdigit()] or [
        i for i, ch in enumerate(value) if ch.isalpha()
    ]
    if not spots:
        return None
    for _ in range(30):
        i = rng.choice(spots)
        ch = value[i]
        if ch.isdigit():
            new = rng.choice([d for d in "0123456789" if d != ch])
        else:
            new = rng.choice([c for c in _SAFE_LETTERS if c != ch.lower()])
            new = new.upper() if ch.isupper() else new
        out = value[:i] + new + value[i + 1:]
        try:
            parse_claim(name, out)
        except ValueError:
            continue
        return out
    return None


def _claim(sample: Sample, name: str, rng: random.Random, silent_fix: float) -> Claim:
    a = sample.anchors[name]
    clean_page = sample.page(a.kind, a.page, clean=True)
    shown_page = sample.page(a.kind, a.page)
    quote, value = a.line, a.value
    # An extractor reading a noisy page either repairs the noise silently or copies it, into the
    # quote and into the value as well.
    copies_noise = rng.random() >= silent_fix
    if shown_page != clean_page and copies_noise:
        start = clean_page.find(a.line)
        quote = shown_page[start:start + len(a.line)]
        value = quote.split(":", 1)[1].strip()
    return Claim(name, value, Citation(f"{sample.sample_id}/{a.kind}", a.page, quote))


def extract(
    sample: Sample,
    rng: random.Random,
    rates: dict[str, float] | None = None,
    silent_fix: float = 0.5,
) -> list[Produced]:
    """The findings a seeded, flawed extractor reports for one sample."""
    rates = rates or {}
    corpus = sample.corpus()
    out: list[Produced] = []
    for attribute, rule in ATTRIBUTES.items():
        draw = rng.random()
        wanted, total = None, 0.0
        for f in FAULTS:
            total += rates.get(f, 0.0)
            if draw < total:
                wanted = f
                break
        claims = [_claim(sample, name, rng, silent_fix) for name in rule.claims]
        pick = rng.randrange(len(claims))
        applied = None
        verdict = None

        if wanted == "wrong_page":
            # only a two-page document has another page to cite
            options = [i for i, c in enumerate(claims) if len(corpus[c.citation.doc_id].pages) > 1]
            if options:
                i = options[pick % len(options)]
                c = claims[i]
                other = c.citation.page % len(corpus[c.citation.doc_id].pages) + 1
                claims[i] = Claim(c.name, c.value, Citation(c.citation.doc_id, other, c.citation.quote))
                applied = wanted
        elif wanted in ("fabricated", "value_drift"):
            c = claims[pick]
            a = sample.anchors[c.name]
            new = perturb(c.name, a.value, rng)
            if new is not None and wanted == "value_drift":
                claims[pick] = Claim(c.name, new, c.citation)
                applied = wanted
            elif new is not None:
                quote = a.line.replace(a.value, new, 1)
                if not any(quote in p for p in corpus[c.citation.doc_id].pages):
                    claims[pick] = Claim(c.name, new, Citation(c.citation.doc_id, c.citation.page, quote))
                    applied = wanted
        elif wanted == "wrong_line":
            options = [i for i, c in enumerate(claims) if c.name in sample.decoys]
            if options:
                i = options[pick % len(options)]
                d = sample.decoys[claims[i].name]
                claims[i] = Claim(claims[i].name, d.value, Citation(
                    f"{sample.sample_id}/{d.kind}", d.page, d.line))
                applied = wanted
        elif wanted == "verdict_flip":
            verdict = "pass" if sample.truth[attribute] == "exception" else "exception"
            applied = wanted

        if verdict is None:
            try:
                verdict = rule.decide({c.name: c.value for c in claims})
            except ValueError:
                verdict = sample.truth[attribute]
        out.append(Produced(
            Finding(sample.sample_id, attribute, tuple(claims), verdict), applied, sample.truth[attribute]))
    return out
