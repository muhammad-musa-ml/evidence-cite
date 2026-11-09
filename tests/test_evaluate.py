import contextlib
import io
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from evidence_cite.evaluate import cell, evaluate, main, render
from evidence_cite.simulate import FAULTS

SEEDS = (1, 2)
N = 80
NOISES = (0.0, 0.05)
RATES = {f: 0.03 for f in FAULTS}


class EvaluateTests(unittest.TestCase):
    R = evaluate(SEEDS, N, NOISES, RATES, 0.5)

    def total(self, noise, checker, key):
        return sum(c[key] for c in self.R[(noise, checker)])

    def test_every_run_sees_four_findings_per_sample(self):
        for counters in self.R.values():
            for c in counters:
                self.assertEqual(c["findings"], 4 * N)
                self.assertEqual(c["verified"] + c["weak"] + c["rejected"], c["findings"])

    def test_same_faults_land_on_the_same_findings_at_every_noise_level(self):
        self.assertEqual(self.total(0.0, "trust", "faulty"), self.total(0.05, "trust", "faulty"))

    def test_trusting_the_extractor_lets_every_fault_through(self):
        for noise in NOISES:
            self.assertGreater(self.total(noise, "trust", "faulty"), 20)
            self.assertEqual(self.total(noise, "trust", "faulty_verified"), self.total(noise, "trust", "faulty"))

    def test_both_checkers_let_no_faulty_finding_through_as_verified(self):
        for noise in NOISES:
            for checker in ("exact", "tiered"):
                self.assertEqual(self.total(noise, checker, "faulty_verified"), 0, (noise, checker))

    def test_only_the_tiered_checker_never_verifies_a_wrong_verdict(self):
        for noise in NOISES:
            self.assertEqual(self.total(noise, "tiered", "wrong_verified"), 0, noise)
        # A copied OCR error in a vendor name makes two names differ on the page; exact mode takes
        # the page at its word, so it verifies the verdict that follows, which is wrong.
        self.assertEqual(self.total(0.0, "exact", "wrong_verified"), 0)
        self.assertGreater(self.total(0.05, "exact", "wrong_verified"), 5)

    def test_without_noise_the_two_checkers_agree(self):
        for key in ("verified", "weak", "rejected"):
            self.assertEqual(self.total(0.0, "exact", key), self.total(0.0, "tiered", key), key)
        self.assertEqual(self.total(0.0, "tiered", "weak"), 0)

    def test_with_noise_exact_rejects_clean_findings_and_tiered_sets_them_aside_as_weak(self):
        self.assertGreater(self.total(0.05, "exact", "clean_rejected"), 20)
        self.assertEqual(self.total(0.05, "tiered", "clean_rejected"), 0)
        self.assertGreater(self.total(0.05, "tiered", "clean_weak"), 20)

    def test_trust_reports_wrong_verdicts_as_verified(self):
        self.assertGreater(self.total(0.0, "trust", "wrong_verified"), 0)

    def test_evaluation_is_deterministic(self):
        self.assertEqual(self.R, evaluate(SEEDS, N, NOISES, RATES, 0.5))

    def test_render_has_a_row_per_noise_level_and_checker_and_a_row_per_fault(self):
        text = render(self.R, SEEDS, N, NOISES, RATES, 0.5)
        self.assertEqual(sum(line.startswith("| 0%") or line.startswith("| 5%") for line in text.splitlines()), 6)
        for fault in FAULTS:
            self.assertIn(f"| {fault} |", text)

    def test_render_cells_are_the_shares_in_the_counters(self):
        counts = Counter(findings=10, verified=7, weak=2, rejected=1, clean=8, clean_rejected=1,
                         faulty=2, faulty_verified=0, wrong_verified=1)
        results = {(0.0, checker): [counts] for checker in ("trust", "exact", "tiered")}
        text = render(results, (1,), 5, (0.0,), RATES, 0.5)
        row = next(line for line in text.splitlines() if line.startswith("| 0% | tiered"))
        self.assertEqual(row, "| 0% | tiered | 70.0 (70.0-70.0) | 20.0 (20.0-20.0) | 10.0 (10.0-10.0) "
                              "| 12.5 (12.5-12.5) | 0.0 (0.0-0.0) | 10.0 (10.0-10.0) |")

    def test_the_fault_table_reads_the_highest_noise_level_whatever_the_order(self):
        low = Counter({"findings": 4, "fault:fabricated": 1, "fault:fabricated:rejected": 1})
        high = Counter({"findings": 4, "fault:fabricated": 2, "fault:fabricated:weak": 1,
                        "fault:fabricated:rejected": 1})
        results = {(noise, checker): [counts] for noise, counts in ((0.0, low), (0.05, high))
                   for checker in ("trust", "exact", "tiered")}
        text = render(results, (1,), 1, (0.05, 0.0), RATES, 0.5)
        self.assertIn("| fabricated | 2 | 0 | 1 | 1 |", text)

    def test_a_share_with_nothing_to_divide_by_is_n_a(self):
        counts = Counter(findings=4, verified=4)
        self.assertEqual(cell([counts], "verified", "findings"), "100.0 (100.0-100.0)")
        self.assertEqual(cell([counts], "faulty_verified", "faulty"), "n/a")

    def test_the_fault_table_counts_match_the_run(self):
        text = render(self.R, SEEDS, N, NOISES, RATES, 0.5)
        for fault in FAULTS:
            total = self.total(0.05, "tiered", f"fault:{fault}")
            self.assertIn(f"| {fault} | {total} | 0 | 0 | {total} |", text)

    def test_main_writes_the_table_with_lf_endings(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "table.md"
            with contextlib.redirect_stdout(io.StringIO()):
                main(["--seeds", "1", "--n", "20", "--noise", "0,0.05", "--out", str(out)])
            data = out.read_bytes()
        self.assertIn(b"| tiered |", data)
        self.assertNotIn(b"\r", data)


if __name__ == "__main__":
    unittest.main()
