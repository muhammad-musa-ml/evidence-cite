import unittest

from evidence_cite.models import Citation, Claim, Document, Finding
from evidence_cite.verify import check_claim, verify

PO = "PURCHASE ORDER PO-7\nDate: 2026-03-02\nVendor: Harlow Supply Co\nUnit price: 415.00\nOrder total: 12,450.00"
INV_1 = "INVOICE INV-9\nInvoice date: 2026-03-20\nBill from: Harlow Supply Co\nSubtotal: 12,000.00"
INV_2 = "Freight: 450.00\nTotal due: 12,450.00"


def corpus(po=PO, inv_1=INV_1, inv_2=INV_2):
    return {
        "S1/po": Document("S1/po", (po,)),
        "S1/invoice": Document("S1/invoice", (inv_1, inv_2)),
    }


def claim(name, value, doc, page, quote):
    return Claim(name, value, Citation(f"S1/{doc}", page, quote))


def amount(verdict="pass", **override):
    po = dict(name="po_total", value="12,450.00", doc="po", page=1, quote="Order total: 12,450.00")
    inv = dict(name="invoice_total", value="12,450.00", doc="invoice", page=2, quote="Total due: 12,450.00")
    for key, val in override.items():
        target, field = key.split("__")
        (po if target == "po" else inv)[field] = val
    return Finding("S1", "amount_match", (claim(**po), claim(**inv)), verdict)


def reasons(finding, corp=None, mode="tiered"):
    return verify(finding, corp or corpus(), mode).reasons


class VerifyTests(unittest.TestCase):
    def test_clean_finding_is_verified_and_gives_highlight_spans(self):
        result = verify(amount(), corpus())
        self.assertEqual(result.status, "verified")
        doc_id, page, start, end = result.spans[0]
        self.assertEqual(corpus()[doc_id].pages[page - 1][start:end], "Order total: 12,450.00")

    def test_quote_that_is_not_on_the_page_is_rejected(self):
        f = amount(po__quote="Order total: 12,540.00", po__value="12,540.00", verdict="exception")
        self.assertEqual(reasons(f), ("po_total: quote_not_on_page",))

    def test_quote_found_on_another_page_names_that_page(self):
        self.assertEqual(reasons(amount(inv__page=1)), ("invoice_total: quote_on_page_2",))

    def test_page_past_the_end_is_rejected(self):
        self.assertEqual(reasons(amount(po__page=2)), ("po_total: no_such_page",))

    def test_unknown_and_wrong_documents_are_rejected(self):
        self.assertEqual(reasons(amount(po__doc="missing")), ("po_total: no_such_document",))
        wrong = Finding("S1", "amount_match", (
            Claim("po_total", "12,450.00", Citation("S1/invoice", 2, "Total due: 12,450.00")),
            amount().claims[1],
        ), "pass")
        self.assertEqual(reasons(wrong), ("po_total: wrong_document",))

    def test_a_document_of_another_sample_is_rejected(self):
        other = dict(corpus(), **{"S2/po": Document("S2/po", (PO,))})
        f = Finding("S1", "amount_match", (
            Claim("po_total", "12,450.00", Citation("S2/po", 1, "Order total: 12,450.00")),
            amount().claims[1],
        ), "pass")
        self.assertEqual(reasons(f, other), ("po_total: wrong_sample",))

    def test_value_that_drops_a_leading_digit_is_rejected(self):
        f = amount(po__value="2,450.00", verdict="exception")
        self.assertEqual(reasons(f), ("po_total: value_not_in_quote",))

    def test_real_quote_from_the_wrong_line_is_rejected(self):
        f = amount(inv__quote="Subtotal: 12,000.00", inv__value="12,000.00", inv__page=1, verdict="exception")
        self.assertEqual(reasons(f), ("invoice_total: wrong_line",))

    def test_verdict_that_does_not_follow_from_the_values_is_rejected(self):
        self.assertEqual(reasons(amount(verdict="exception")), ("verdict_mismatch",))

    def test_missing_or_extra_claims_are_rejected(self):
        f = Finding("S1", "amount_match", amount().claims[:1], "pass")
        self.assertEqual(reasons(f), ("claims_mismatch",))
        twice = Finding("S1", "amount_match", (amount().claims[0], amount().claims[0]), "pass")
        self.assertEqual(reasons(twice), ("claims_mismatch",))

    def test_unknown_attribute_is_rejected(self):
        self.assertEqual(reasons(Finding("S1", "tax_match", amount().claims, "pass")), ("unknown_attribute",))

    def test_each_failing_claim_gets_its_reason(self):
        f = amount(po__page=2, inv__quote="Total due: 99.00", inv__value="99.00")
        self.assertEqual(reasons(f), ("po_total: no_such_page", "invoice_total: quote_not_on_page"))

    def test_a_truncated_document_id_is_no_such_document(self):
        f = Finding("S1", "amount_match", (
            Claim("po_total", "12,450.00", Citation("S1", 1, "Order total: 12,450.00")),
            amount().claims[1],
        ), "pass")
        self.assertEqual(reasons(f), ("po_total: no_such_document",))

    def test_value_that_will_not_parse_is_rejected_in_exact_mode(self):
        noisy = corpus(po=PO.replace("12,450.00", "1O,450.00"), inv_2=INV_2.replace("12,450.00", "1O,450.00"))
        f = amount(po__quote="Order total: 1O,450.00", po__value="1O,450.00",
                   inv__quote="Total due: 1O,450.00", inv__value="1O,450.00")
        self.assertEqual(reasons(f, noisy, "exact"), ("value_unparseable",))
        # tiered mode reads the folded values, and says so
        result = verify(f, noisy)
        self.assertEqual((result.status, result.reasons), ("weak", ("verdict_depends_on_ocr_reading",)))

    def test_a_value_that_will_not_parse_even_folded_is_rejected(self):
        noisy = corpus(po=PO.replace("12,450.00", "12,4X0.00"))
        f = amount(po__quote="Order total: 12,4X0.00", po__value="12,4X0.00")
        self.assertEqual(reasons(f, noisy), ("value_unparseable",))

    def test_unknown_mode_is_an_error(self):
        with self.assertRaises(ValueError):
            verify(amount(), corpus(), mode="loose")


class WholeLineTests(unittest.TestCase):
    """A quote that is true but cuts the line, or joins two lines, must not stand."""

    def test_a_quote_that_cuts_the_number_short_is_rejected(self):
        for quote, value in (("Order total: 12", "12"), ("Order total: 12,450", "12,450")):
            f = amount(po__quote=quote, po__value=value, verdict="exception")
            self.assertEqual(reasons(f), ("po_total: quote_not_whole_line",), quote)

    def test_a_quote_that_starts_inside_the_line_is_rejected(self):
        f = amount(po__quote="total: 12,450.00")
        self.assertEqual(reasons(f), ("po_total: quote_not_whole_line",))

    def test_a_quote_over_two_lines_is_rejected(self):
        f = amount(inv__quote="Freight: 450.00\nTotal due: 12,450.00", inv__value="450.00", verdict="exception")
        self.assertEqual(reasons(f), ("invoice_total: quote_spans_lines",))

    def test_a_value_that_is_only_part_of_the_line_is_rejected(self):
        page = PO.replace("Vendor: Harlow Supply Co", "Vendor: Harlow Supply Co Holdings")
        f = Finding("S1", "vendor_match", (
            claim("po_vendor", "Harlow Supply Co", "po", 1, "Vendor: Harlow Supply Co Holdings"),
            claim("invoice_vendor", "Harlow Supply Co", "invoice", 1, "Bill from: Harlow Supply Co"),
        ), "pass")
        self.assertEqual(reasons(f, corpus(po=page)), ("po_vendor: value_not_in_quote",))

    def test_a_sign_or_bracket_in_front_of_the_value_is_not_the_value(self):
        for shown in ("-12,450.00", "(12,450.00)", "12,450.00-"):
            page = PO.replace("Order total: 12,450.00", f"Order total: {shown}")
            f = amount(po__quote=f"Order total: {shown}")
            self.assertEqual(reasons(f, corpus(po=page)), ("po_total: value_not_in_quote",), shown)

    def test_a_label_that_only_ends_a_longer_label_is_rejected(self):
        page = PO.replace("Date: 2026-03-02", "Delivery date: 2026-03-04")
        f = Finding("S1", "invoice_after_po", (
            claim("po_date", "2026-03-04", "po", 1, "Delivery date: 2026-03-04"),
            claim("invoice_date", "2026-03-20", "invoice", 1, "Invoice date: 2026-03-20"),
        ), "pass")
        self.assertEqual(reasons(f, corpus(po=page)), ("po_date: wrong_line",))

    def test_extra_spaces_and_case_in_the_quote_are_fine(self):
        f = amount(po__quote="  order   TOTAL:  12,450.00 ")
        self.assertEqual(verify(f, corpus()).status, "verified")


class RepeatedLabelTests(unittest.TestCase):
    TWO_TOTALS = PO + "\nOrder total: 13,200.00"

    def test_a_page_with_two_different_values_for_the_label_is_weak_in_both_modes(self):
        for mode in ("exact", "tiered"):
            result = verify(amount(), corpus(po=self.TWO_TOTALS), mode)
            self.assertEqual((result.status, result.reasons), ("weak", ("po_total: ambiguous_label",)), mode)

    def test_a_repeated_line_with_the_same_value_is_not_ambiguous(self):
        self.assertEqual(verify(amount(), corpus(po=PO + "\nOrder total: 12,450.00")).status, "verified")

    def test_a_longer_line_that_ends_like_the_quote_does_not_hide_the_whole_line(self):
        inv_2 = "Previous Total due: 12,450.00\n" + INV_2
        self.assertEqual(verify(amount(), corpus(inv_2=inv_2)).status, "verified")

    def test_the_other_line_does_not_count_when_it_has_another_label(self):
        self.assertEqual(verify(amount(), corpus(po=PO + "\nUnit price: 13,200.00")).status, "verified")

    def test_the_span_is_the_cited_line_not_its_twin(self):
        result = verify(amount(po__quote="Order total: 13,200.00", po__value="13,200.00", verdict="exception"),
                        corpus(po=self.TWO_TOTALS))
        doc_id, page, start, end = result.spans[0] if result.spans[0][0] == "S1/po" else result.spans[1]
        self.assertEqual(self.TWO_TOTALS[start:end], "Order total: 13,200.00")


class SpanTests(unittest.TestCase):
    def test_a_rejected_finding_keeps_the_spans_of_the_claims_that_stand(self):
        result = verify(amount(inv__quote="Total due: 99.00", inv__value="99.00"), corpus())
        self.assertEqual(result.status, "rejected")
        self.assertEqual(len(result.spans), 1)
        doc_id, page, start, end = result.spans[0]
        self.assertEqual((doc_id, PO[start:end]), ("S1/po", "Order total: 12,450.00"))

    def test_a_finding_rejected_for_its_verdict_keeps_every_span(self):
        self.assertEqual(len(verify(amount(verdict="exception"), corpus()).spans), 2)


class OtherPageTests(unittest.TestCase):
    NOISY_P2 = corpus(inv_2=INV_2.replace("Total due: 12,450.00", "T0tal due: l2,450.00"))

    def test_tiered_mode_finds_a_noisy_quote_on_the_other_page_and_exact_mode_does_not(self):
        f = amount(inv__page=1)
        self.assertEqual(reasons(f, self.NOISY_P2), ("invoice_total: quote_on_page_2",))
        self.assertEqual(reasons(f, self.NOISY_P2, "exact"), ("invoice_total: quote_not_on_page",))


class OcrVerdictTests(unittest.TestCase):
    """Two names that differ only by look-alike characters: the page says one thing, the folded reading another."""

    NOISY = corpus(po=PO.replace("Vendor: Harlow Supply Co", "Vendor: Harlow SuppIy Co"))

    def vendor(self, verdict, po_name="Harlow SuppIy Co", inv_name="Harlow Supply Co"):
        return Finding("S1", "vendor_match", (
            claim("po_vendor", po_name, "po", 1, f"Vendor: {po_name}"),
            claim("invoice_vendor", inv_name, "invoice", 1, f"Bill from: {inv_name}"),
        ), verdict)

    def test_the_verdict_the_page_text_gives_is_verified_by_exact_mode_and_weak_by_tiered(self):
        f = self.vendor("exception")
        self.assertEqual(verify(f, self.NOISY, "exact").status, "verified")
        result = verify(f, self.NOISY)
        self.assertEqual((result.status, result.reasons), ("weak", ("verdict_depends_on_ocr_reading",)))

    def test_the_verdict_the_folded_reading_gives_is_rejected_by_exact_mode_and_weak_by_tiered(self):
        f = self.vendor("pass")
        self.assertEqual(reasons(f, self.NOISY, "exact"), ("verdict_mismatch",))
        self.assertEqual(verify(f, self.NOISY).status, "weak")

    def test_a_verdict_neither_reading_gives_is_rejected(self):
        both_differ = self.vendor("pass", po_name="Brightwater Logistics")
        both = dict(self.NOISY, **{"S1/po": Document("S1/po", (PO.replace("Harlow Supply Co", "Brightwater Logistics"),))})
        self.assertEqual(reasons(both_differ, both), ("verdict_mismatch",))

    def test_clearly_different_vendors_stay_verified(self):
        po = PO.replace("Harlow Supply Co", "Brightwater Logistics")
        f = self.vendor("exception", po_name="Brightwater Logistics")
        self.assertEqual(verify(f, corpus(po=po)).status, "verified")


class OcrTierTests(unittest.TestCase):
    NOISY = corpus(po=PO.replace("Order total: 12,450.00", "Order t0tal: l2,450.00"))
    LABEL_ONLY = corpus(po=PO.replace("Order total: 12,450.00", "Order t0tal: 12,450.00"))

    def test_clean_quote_over_a_noisy_page_is_weak_in_tiered_mode(self):
        result = verify(amount(), self.NOISY)
        self.assertEqual(result.status, "weak")
        self.assertEqual(result.reasons, ("po_total: ocr_confusion",))

    def test_same_finding_is_rejected_in_exact_mode(self):
        self.assertEqual(reasons(amount(), self.NOISY, "exact"), ("po_total: quote_not_on_page",))

    def test_verbatim_noisy_quote_with_clean_value_is_weak(self):
        f = amount(po__quote="Order t0tal: l2,450.00")
        self.assertEqual(verify(f, self.NOISY).status, "weak")
        self.assertEqual(reasons(f, self.NOISY, "exact"), ("po_total: wrong_line",))

    def test_a_label_that_matches_only_after_the_fold_makes_the_claim_weak(self):
        f = amount(po__quote="Order t0tal: 12,450.00")
        self.assertEqual(verify(f, self.LABEL_ONLY).status, "weak")
        self.assertEqual(reasons(f, self.LABEL_ONLY, "exact"), ("po_total: wrong_line",))

    def test_fold_never_turns_a_wrong_digit_into_a_match(self):
        f = amount(po__quote="Order total: 12,458.00", po__value="12,458.00", verdict="exception")
        self.assertEqual(verify(f, self.NOISY).status, "rejected")

    def test_check_claim_reports_the_tier(self):
        c = amount().claims[0]
        self.assertEqual(check_claim(c, self.NOISY).tier, "folded")
        self.assertEqual(check_claim(c, corpus()).tier, "exact")

    def test_the_span_of_a_folded_claim_points_at_the_noisy_page_text(self):
        result = verify(amount(), self.NOISY)
        doc_id, page, start, end = result.spans[0]
        self.assertEqual(self.NOISY[doc_id].pages[page - 1][start:end], "Order t0tal: l2,450.00")


if __name__ == "__main__":
    unittest.main()
