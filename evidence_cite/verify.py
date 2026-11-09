from __future__ import annotations

from dataclasses import dataclass

from .attributes import ATTRIBUTES, CLAIMS
from .models import Claim, Document, Finding
from .text import locate, normalise

MODES = ("exact", "tiered")


@dataclass(frozen=True)
class ClaimCheck:
    reason: str  # "" when the claim stands
    tier: str  # "exact", "folded" or "" when rejected
    span: tuple  # (doc_id, page, start, end) in the original page, for highlighting
    ambiguous: bool = False  # another line of the page has the same label and a different value


@dataclass(frozen=True)
class Result:
    status: str  # "verified", "weak" or "rejected"
    reasons: tuple[str, ...]
    spans: tuple[tuple, ...]  # the spans of the claims that stand, also when the finding is rejected


def _reject(reason: str) -> ClaimCheck:
    return ClaimCheck(reason, "", ())


def _decide(rule, values: dict[str, str]) -> str | None:
    try:
        return rule.decide(values)
    except ValueError:
        return None


def _lines(page: str):
    """(start, end, text) of each non-empty line, without the whitespace around it."""
    pos = 0
    for raw in page.split("\n"):
        text = raw.strip()
        if text:
            start = pos + len(raw) - len(raw.lstrip())
            yield start, start + len(text), text
        pos += len(raw) + 1


def _on_page(page: str, claim: Claim, label: str, fold: bool) -> tuple[str, tuple, bool]:
    """Check the claim against one page with one setting of the OCR fold: (reason, span, ambiguous)."""
    quote, _ = normalise(claim.citation.quote, fold)
    wanted, _ = normalise(label, fold)
    value, _ = normalise(claim.value, fold)
    lines = [(start, end, normalise(text, fold)[0]) for start, end, text in _lines(page)]

    # The quote has to be one whole line, so a number cut short or two lines joined cannot pass.
    hits = [(start, end, line) for start, end, line in lines if quote and line == quote]
    if not hits:
        span = locate(page, claim.citation.quote, fold)
        if span is None:
            return "quote_not_on_page", (), False
        if "\n" in page[span[0]:span[1]]:
            return "quote_spans_lines", (), False
        return "quote_not_whole_line", (), False
    start, end, line = hits[0]
    if not line.startswith(wanted):
        return "wrong_line", (), False
    if not value or line[len(wanted):].strip() != value:
        return "value_not_in_quote", (), False
    rivals = {other[len(wanted):].strip() for s, e, other in lines
              if (s, e) != (start, end) and other.startswith(wanted)}
    return "", (start, end), any(r != value for r in rivals)


def check_claim(
    claim: Claim, corpus: dict[str, Document], mode: str = "tiered", sample_id: str | None = None
) -> ClaimCheck:
    """Check one claim against the page it cites.

    The cited line must be a whole line of that page, start with the label the claim
    needs, and carry exactly the claimed value after it.

    exact:  the match is made after case, whitespace and Unicode normalisation only.
    tiered: as exact, and when that fails, again with OCR look-alikes folded; a claim
            that needs the fold stands as "folded", for a person to confirm.

    A claim whose page holds another line with the same label and a different value is
    marked ambiguous, in either mode.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r}")
    spec = CLAIMS.get(claim.name)
    if spec is None:
        return _reject("unknown_claim")
    kind, label = spec
    cite = claim.citation
    doc = corpus.get(cite.doc_id)
    if doc is None:
        return _reject("no_such_document")
    if sample_id is not None and not cite.doc_id.startswith(f"{sample_id}/"):
        return _reject("wrong_sample")
    if cite.doc_id.rsplit("/", 1)[-1] != kind:
        return _reject("wrong_document")
    if not 1 <= cite.page <= len(doc.pages):
        return _reject("no_such_page")

    page = doc.pages[cite.page - 1]
    reason = ""
    for fold in (False,) if mode == "exact" else (False, True):
        reason, span, ambiguous = _on_page(page, claim, label, fold)
        if not reason:
            return ClaimCheck("", "folded" if fold else "exact", (cite.doc_id, cite.page, *span), ambiguous)
    if reason == "quote_not_on_page":
        for n, other in enumerate(doc.pages, 1):
            if n != cite.page and locate(other, cite.quote, mode == "tiered"):
                return _reject(f"quote_on_page_{n}")
    return _reject(reason)


def verify(finding: Finding, corpus: dict[str, Document], mode: str = "tiered") -> Result:
    """Verified: every claim is on its page and the verdict follows from the claimed values.

    Weak: as verified, but a person should look: a claim needed the OCR fold, a page holds
    two lines with the claim's label and different values, or (tiered mode) the verdict
    depends on how the look-alike characters are read.
    Rejected: anything else, with the reason for each claim that failed.
    """
    rule = ATTRIBUTES.get(finding.attribute)
    if rule is None:
        return Result("rejected", ("unknown_attribute",), ())
    if tuple(sorted(c.name for c in finding.claims)) != rule.claims:
        return Result("rejected", ("claims_mismatch",), ())

    checks = [(c, check_claim(c, corpus, mode, finding.sample_id)) for c in finding.claims]
    spans = tuple(k.span for _, k in checks if k.span)
    reasons = tuple(f"{c.name}: {k.reason}" for c, k in checks if k.reason)
    if reasons:
        return Result("rejected", reasons, spans)

    # The verdict is recomputed from the claimed values as written. In tiered mode it is also
    # recomputed with the look-alikes folded; a reported verdict is accepted if either reading
    # gives it, and the finding is weak when the answer depends on which reading is right.
    values = {c.name: c.value for c in finding.claims}
    as_written = _decide(rule, values)
    readings = {as_written}
    if mode == "tiered":
        readings.add(_decide(rule, {name: normalise(v, True)[0] for name, v in values.items()}))
    readings.discard(None)
    if not readings:
        return Result("rejected", ("value_unparseable",), spans)
    if finding.verdict not in readings:
        return Result("rejected", ("verdict_mismatch",), spans)

    weak = tuple(f"{c.name}: ocr_confusion" for c, k in checks if k.tier == "folded")
    weak += tuple(f"{c.name}: ambiguous_label" for c, k in checks if k.ambiguous)
    if len(readings) > 1 or as_written is None:
        weak += ("verdict_depends_on_ocr_reading",)
    if weak:
        return Result("weak", weak, spans)
    return Result("verified", (), spans)
