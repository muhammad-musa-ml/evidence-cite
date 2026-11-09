import random
import unittest

from evidence_cite.attributes import ATTRIBUTES, CLAIMS
from evidence_cite.synth import CONFUSABLE, add_noise, make_population
from evidence_cite.text import FOLD, normalise


class PopulationTests(unittest.TestCase):
    POP = make_population(1, 300)

    def test_same_seed_gives_the_same_population(self):
        self.assertEqual(make_population(1, 20), make_population(1, 20))

    def test_different_seeds_differ(self):
        self.assertNotEqual(make_population(1, 20), make_population(2, 20))

    def test_truth_is_what_the_rules_say_about_the_anchor_values(self):
        for s in self.POP:
            for attribute, rule in ATTRIBUTES.items():
                values = {name: s.anchors[name].value for name in rule.claims}
                self.assertEqual(rule.decide(values), s.truth[attribute], (s.sample_id, attribute))

    def test_each_anchor_line_is_on_its_page_exactly_once_with_its_value(self):
        for s in self.POP:
            for group in (s.anchors, s.decoys):
                for name, a in group.items():
                    page = s.page(a.kind, a.page, clean=True)
                    self.assertEqual(page.count(a.line), 1, (s.sample_id, name))
                    self.assertIn(a.value, a.line)

    def test_anchors_use_the_document_kind_the_claim_spec_expects(self):
        for s in self.POP[:20]:
            for name, a in s.anchors.items():
                self.assertEqual(a.kind, CLAIMS[name][0])
                self.assertTrue(a.line.lower().startswith(CLAIMS[name][1]))

    def test_exception_rate_is_near_the_request(self):
        flags = [v == "exception" for s in self.POP for v in s.truth.values()]
        share = sum(flags) / len(flags)
        self.assertTrue(0.05 < share < 0.11, share)

    def test_every_attribute_has_both_outcomes(self):
        for attribute in ATTRIBUTES:
            self.assertEqual({s.truth[attribute] for s in self.POP}, {"pass", "exception"})

    def test_invoice_has_two_pages_and_the_decoys_are_real_lines(self):
        s = self.POP[0]
        self.assertEqual(len(s.corpus()[f"{s.sample_id}/invoice"].pages), 2)
        self.assertEqual(set(s.decoys), {"po_total", "invoice_total"})


class NoiseTests(unittest.TestCase):
    S = make_population(3, 60)

    def test_rate_zero_returns_the_sample_unchanged(self):
        s = self.S[0]
        self.assertIs(add_noise(s, 0, random.Random(0)), s)

    def test_noise_keeps_length_and_changes_only_confusable_characters(self):
        rng = random.Random(5)
        changed = 0
        for s in self.S:
            noisy = add_noise(s, 0.2, rng)
            for clean_doc, noisy_doc in zip(noisy.clean, noisy.docs):
                for c_page, n_page in zip(clean_doc.pages, noisy_doc.pages):
                    self.assertEqual(len(c_page), len(n_page))
                    for c, n in zip(c_page, n_page):
                        if c != n:
                            changed += 1
                            self.assertTrue(any(c in g and n in g for g in CONFUSABLE), (c, n))
        self.assertGreater(changed, 0)

    def test_noise_rate_matches_the_request_on_confusable_characters(self):
        rng = random.Random(9)
        eligible = changed = 0
        for s in self.S:
            noisy = add_noise(s, 0.05, rng)
            for c_doc, n_doc in zip(noisy.clean, noisy.docs):
                for c_page, n_page in zip(c_doc.pages, n_doc.pages):
                    for c, n in zip(c_page, n_page):
                        if any(c in g for g in CONFUSABLE):
                            eligible += 1
                            changed += c != n
        self.assertTrue(0.04 < changed / eligible < 0.06, changed / eligible)

    def test_fold_undoes_the_noise(self):
        rng = random.Random(11)
        for s in self.S[:20]:
            noisy = add_noise(s, 0.3, rng)
            for c_doc, n_doc in zip(noisy.clean, noisy.docs):
                for c_page, n_page in zip(c_doc.pages, n_doc.pages):
                    self.assertEqual(normalise(c_page, fold=True)[0], normalise(n_page, fold=True)[0])

    def test_every_confusable_character_is_folded_by_the_checker(self):
        for group in CONFUSABLE:
            self.assertEqual(len({FOLD.get(c.lower(), c.lower()) for c in group}), 1, group)


if __name__ == "__main__":
    unittest.main()
