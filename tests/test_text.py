import unittest

from evidence_cite.text import locate, normalise


class NormaliseTests(unittest.TestCase):
    def test_collapses_whitespace_and_case(self):
        text, _ = normalise("  Order   TOTAL:\n 12,450.00  ")
        self.assertEqual(text, "order total: 12,450.00")

    def test_ligature_expands_and_maps_back_to_one_offset(self):
        text, idx = normalise("ofﬁce")
        self.assertEqual(text, "office")
        self.assertEqual(idx, [0, 1, 2, 2, 3, 4])

    def test_fold_maps_look_alikes_to_digits(self):
        folded, _ = normalise("l0,5OO.0S", fold=True)
        plain, _ = normalise("10,500.05", fold=True)
        self.assertEqual(folded, plain)

    def test_fold_off_keeps_letters(self):
        text, _ = normalise("l0")
        self.assertEqual(text, "l0")

    def test_a_letter_and_its_combining_mark_equal_the_composed_letter(self):
        self.assertEqual(normalise("Café")[0], normalise("Café")[0])

    def test_casefold_equates_sharp_s_with_ss(self):
        self.assertEqual(normalise("Straße")[0], normalise("STRASSE")[0])

    def test_a_base_letter_and_its_mark_become_one_character_with_one_start_offset(self):
        text, idx = normalise("éx")
        self.assertEqual((text, idx), ("éx", [0, 2]))


class LocateTests(unittest.TestCase):
    PAGE = "PURCHASE ORDER PO-7\nDate: 2026-03-02\nOrder total:   12,450.00\nVendor: Harlow Supply Co"

    def test_span_points_into_the_original_page(self):
        span = locate(self.PAGE, "order total: 12,450.00")
        self.assertIsNotNone(span)
        self.assertEqual(self.PAGE[span[0]:span[1]], "Order total:   12,450.00")

    def test_a_span_that_ends_on_a_combining_mark_includes_the_mark(self):
        page = "Café au lait"
        span = locate(page, "Café")
        self.assertEqual(page[span[0]:span[1]], "Café")

    def test_missing_quote_is_none(self):
        self.assertIsNone(locate(self.PAGE, "Order total: 12,540.00"))

    def test_empty_quote_is_none(self):
        self.assertIsNone(locate(self.PAGE, "   "))

    def test_a_quote_may_run_across_a_line_break(self):
        span = locate(self.PAGE, "Date: 2026-03-02 Order total: 12,450.00")
        self.assertIsNotNone(span)
        self.assertIn("\n", self.PAGE[span[0]:span[1]])

    def test_ocr_noise_needs_fold(self):
        noisy = "Order t0tal: l2,450.0O"
        self.assertIsNone(locate(noisy, "Order total: 12,450.00"))
        span = locate(noisy, "Order total: 12,450.00", fold=True)
        self.assertEqual(span, (0, len(noisy)))

    def test_fold_does_not_equate_different_digits(self):
        self.assertIsNone(locate("Total due: 12,450.00", "Total due: 12,458.00", fold=True))


if __name__ == "__main__":
    unittest.main()
