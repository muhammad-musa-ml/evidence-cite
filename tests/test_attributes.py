import unittest
from decimal import Decimal

from evidence_cite.attributes import (
    ATTRIBUTES,
    CLAIMS,
    parse_claim,
    parse_date,
    parse_money,
    parse_name,
)


class ParseTests(unittest.TestCase):
    def test_money_forms(self):
        self.assertEqual(parse_money("12,450.00"), Decimal("12450.00"))
        self.assertEqual(parse_money("$300"), Decimal("300"))

    def test_money_rejects_misgrouped_and_look_alike_text(self):
        for bad in ("12,45.00", "1O,540.00", "l2,450.00", "12,450.0", "", "12.450,00"):
            with self.assertRaises(ValueError, msg=bad):
                parse_money(bad)

    def test_date_rejects_impossible_and_loose_forms(self):
        self.assertEqual(parse_date("2026-03-02").day, 2)
        for bad in ("2026-13-02", "2026-02-30", "20260302", "2026-3-2", "2O26-03-02"):
            with self.assertRaises(ValueError, msg=bad):
                parse_date(bad)

    def test_name_is_case_and_space_insensitive(self):
        self.assertEqual(parse_name(" Harlow  SUPPLY Co "), "harlow supply co")
        with self.assertRaises(ValueError):
            parse_name("  ")

    def test_parse_claim_dispatches_by_name(self):
        parse_claim("po_total", "1,000.00")
        with self.assertRaises(ValueError):
            parse_claim("invoice_date", "1,000.00")


class RuleTests(unittest.TestCase):
    def decide(self, attribute, **values):
        return ATTRIBUTES[attribute].decide(values)

    def test_amount_match(self):
        self.assertEqual(self.decide("amount_match", po_total="1,000.00", invoice_total="1000.00"), "pass")
        self.assertEqual(self.decide("amount_match", po_total="1,000.00", invoice_total="1,000.01"), "exception")

    def test_invoice_after_po(self):
        self.assertEqual(self.decide("invoice_after_po", po_date="2026-03-02", invoice_date="2026-03-02"), "pass")
        self.assertEqual(self.decide("invoice_after_po", po_date="2026-03-02", invoice_date="2026-03-01"), "exception")

    def test_approval_within_limit(self):
        self.assertEqual(self.decide("approval_within_limit", po_total="2,500.00", approver_limit="2,500.00"), "pass")
        self.assertEqual(self.decide("approval_within_limit", po_total="2,500.01", approver_limit="2,500.00"), "exception")

    def test_vendor_match(self):
        self.assertEqual(self.decide("vendor_match", po_vendor="Harlow Supply Co", invoice_vendor="harlow supply co"), "pass")
        self.assertEqual(self.decide("vendor_match", po_vendor="Harlow Supply Co", invoice_vendor="Harlow Supply Corp"), "exception")

    def test_unparseable_value_raises_instead_of_guessing(self):
        with self.assertRaises(ValueError):
            self.decide("amount_match", po_total="1O,000.00", invoice_total="10,000.00")


class SpecTests(unittest.TestCase):
    def test_every_rule_claim_has_a_document_kind_and_label(self):
        for name, rule in ATTRIBUTES.items():
            self.assertEqual(list(rule.claims), sorted(rule.claims), name)
            for claim in rule.claims:
                kind, label = CLAIMS[claim]
                self.assertIn(kind, ("po", "invoice", "approval"))
                self.assertTrue(label.endswith(":"))


if __name__ == "__main__":
    unittest.main()
