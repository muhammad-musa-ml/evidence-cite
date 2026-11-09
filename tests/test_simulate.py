import random
import unittest
from collections import Counter
from datetime import date

from evidence_cite.simulate import FAULTS, extract, perturb
from evidence_cite.synth import add_noise, make_population
from evidence_cite.text import normalise
from evidence_cite.verify import verify

POP = make_population(4, 120)


def run(rates, noise=0.0, silent_fix=0.5, seed=1):
    rng = random.Random(seed)
    out = []
    for s in POP:
        shown = add_noise(s, noise, random.Random(f"{seed}-{s.sample_id}"))
        out.extend((p, shown.corpus()) for p in extract(shown, rng, rates, silent_fix))
    return out


class PerturbTests(unittest.TestCase):
    def test_changes_one_character_and_keeps_the_kind(self):
        rng = random.Random(0)
        for name, value in (("po_total", "12,450.00"), ("po_date", "2026-03-02"), ("po_vendor", "Harlow Supply Co")):
            for _ in range(200):
                new = perturb(name, value, rng)
                self.assertIsNotNone(new)
                self.assertNotEqual(new, value)
                self.assertEqual(len(new), len(value))
                self.assertEqual(sum(a != b for a, b in zip(new, value)), 1)

    def test_a_swap_is_never_a_look_alike_of_the_original(self):
        rng = random.Random(2)
        cases = (("po_vendor", "Alder & Finch Tools"), ("po_vendor", "Sable Ridge Freight"),
                 ("po_total", "12,450.00"), ("po_date", "2026-03-02"))
        for name, value in cases:
            for _ in range(300):
                new = perturb(name, value, rng)
                self.assertNotEqual(normalise(new, fold=True)[0], normalise(value, fold=True)[0], (value, new))

    def test_a_date_swap_is_always_a_real_date(self):
        rng = random.Random(1)
        for _ in range(300):
            new = perturb("po_date", "2026-03-02", rng)
            date.fromisoformat(new)  # raises on 2026-13-02 and the like


class ExtractTests(unittest.TestCase):
    def test_no_faults_and_no_noise_means_every_finding_verifies_with_the_true_verdict(self):
        for p, corpus in run({}):
            self.assertIsNone(p.fault)
            self.assertEqual(p.finding.verdict, p.truth)
            self.assertEqual(verify(p.finding, corpus).status, "verified")

    def test_same_seed_gives_the_same_findings(self):
        self.assertEqual([p for p, _ in run({"fabricated": 0.3})], [p for p, _ in run({"fabricated": 0.3})])

    def test_each_fault_is_applied_when_asked_and_rejected_by_both_checkers(self):
        for fault in FAULTS:
            produced = run({fault: 1.0})
            applied = [(p, c) for p, c in produced if p.fault == fault]
            self.assertGreater(len(applied), 50, fault)
            for p, corpus in applied:
                for mode in ("exact", "tiered"):
                    self.assertEqual(verify(p.finding, corpus, mode).status, "rejected", (fault, mode))

    def test_wrong_line_only_touches_claims_that_have_a_decoy(self):
        applied = [p for p, _ in run({"wrong_line": 1.0}) if p.fault]
        self.assertEqual({p.finding.attribute for p in applied}, {"amount_match", "approval_within_limit"})

    def test_verdict_flip_changes_only_the_verdict(self):
        flipped, plain = run({"verdict_flip": 1.0}), run({})
        self.assertEqual(len(flipped), len(plain))
        for (f, _), (p, _) in zip(flipped, plain):
            self.assertEqual(f.fault, "verdict_flip")
            self.assertNotEqual(f.finding.verdict, f.truth)
            self.assertEqual(f.finding.claims, p.finding.claims)

    def test_wrong_page_only_touches_claims_on_a_two_page_document(self):
        applied = [p for p, _ in run({"wrong_page": 1.0}) if p.fault]
        self.assertEqual({p.finding.attribute for p in applied},
                         {"amount_match", "invoice_after_po", "vendor_match"})
        for p in applied:
            moved = [c for c in p.finding.claims if c.citation.doc_id.endswith("/invoice")
                     and c.citation.page != {"invoice_total": 2}.get(c.name, 1)]
            self.assertEqual(len(moved), 1)

    def test_fault_rates_are_respected(self):
        faults = Counter(p.fault for p, _ in run({"fabricated": 0.1, "value_drift": 0.1}))
        total = sum(faults.values())
        self.assertTrue(0.07 < faults["fabricated"] / total < 0.13)
        self.assertTrue(0.07 < faults["value_drift"] / total < 0.13)
        self.assertEqual(faults["wrong_page"], 0)

    def test_noise_with_silent_repair_is_weak_not_rejected_by_the_tiered_checker(self):
        statuses = Counter()
        for p, corpus in run({}, noise=0.1, silent_fix=1.0):
            statuses[verify(p.finding, corpus, "tiered").status] += 1
            self.assertNotEqual(verify(p.finding, corpus, "tiered").status, "rejected")
        self.assertGreater(statuses["weak"], 0)

    def test_a_copied_noisy_quote_carries_the_noisy_value_and_a_repaired_one_the_clean_value(self):
        copied = run({}, noise=0.3, silent_fix=0.0)
        repaired = run({}, noise=0.3, silent_fix=1.0)
        noisy_values = 0
        for (c, _), (r, _) in zip(copied, repaired):
            for a, b in zip(c.finding.claims, r.finding.claims):
                self.assertEqual(a.value, a.citation.quote.split(":", 1)[1].strip())  # as the page prints it
                self.assertEqual(b.value, b.citation.quote.split(":", 1)[1].strip())
                noisy_values += a.value != b.value
        self.assertGreater(noisy_values, 50)

    def test_faults_land_on_the_same_findings_at_every_noise_level(self):
        rates = {"fabricated": 0.2, "value_drift": 0.2}
        quiet = [(p.finding.sample_id, p.finding.attribute, p.fault) for p, _ in run(rates, noise=0.0)]
        noisy = [(p.finding.sample_id, p.finding.attribute, p.fault) for p, _ in run(rates, noise=0.2)]
        self.assertEqual(quiet, noisy)
        self.assertGreater(sum(f is not None for _, _, f in quiet), 50)

    def test_the_exact_checker_rejects_clean_findings_on_noisy_pages(self):
        rejected = sum(verify(p.finding, c, "exact").status == "rejected" for p, c in run({}, noise=0.1))
        self.assertGreater(rejected, 0)


if __name__ == "__main__":
    unittest.main()
