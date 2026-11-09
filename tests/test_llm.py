import contextlib
import io
import json
import random
import tempfile
import unittest
from pathlib import Path

from evidence_cite.attributes import ATTRIBUTES, CLAIMS
from evidence_cite.llm import (
    build_prompt, describe, main, pages_digest, parse, render, run, score, shown_population,
)
from evidence_cite.simulate import extract


def reply(produced):
    return json.dumps({"findings": [
        {
            "attribute": p.finding.attribute,
            "verdict": p.finding.verdict,
            "claims": [
                {"name": c.name, "value": c.value, "doc_id": c.citation.doc_id,
                 "page": c.citation.page, "quote": c.citation.quote}
                for c in p.finding.claims
            ],
        }
        for p in produced
    ]})


def fake_model(n, seed, noise, rates, silent_fix=0.5):
    """A model that answers each prompt with the simulator's findings for that sample."""
    answers = {}
    rng = random.Random(7)
    for shown in shown_population(seed, n, noise):
        answers[build_prompt(shown)] = reply(extract(shown, rng, rates, silent_fix))
    return answers.__getitem__


class PromptTests(unittest.TestCase):
    SAMPLE = shown_population(1, 1, 0.0)[0]

    def test_prompt_shows_every_document_page_verbatim(self):
        prompt = build_prompt(self.SAMPLE)
        for doc in self.SAMPLE.docs:
            for i, page in enumerate(doc.pages, 1):
                self.assertIn(f"Document {doc.doc_id}, page {i}:\n{page}", prompt)

    def test_prompt_says_where_each_claim_comes_from(self):
        prompt = build_prompt(self.SAMPLE)
        for name, (kind, label) in CLAIMS.items():
            self.assertIn(f'- {name}: the line labelled "{label.capitalize()}" in the {kind} document', prompt)

    def test_prompt_states_each_attribute_and_its_rule(self):
        prompt = build_prompt(self.SAMPLE)
        for name, rule in ATTRIBUTES.items():
            self.assertIn(f"- {name} (claims: {', '.join(rule.claims)}): ", prompt)


class ShownPopulationTests(unittest.TestCase):
    def test_noise_does_not_depend_on_how_many_samples_follow(self):
        self.assertEqual(shown_population(1, 5, 0.1)[:3], shown_population(1, 3, 0.1))

    def test_noise_differs_between_levels_and_zero_changes_nothing(self):
        clean, noisy = shown_population(1, 5, 0.0), shown_population(1, 5, 0.1)
        self.assertEqual([s.docs for s in clean], [s.clean for s in clean])
        self.assertNotEqual([s.docs for s in noisy], [s.docs for s in clean])

    def test_the_model_is_asked_about_exactly_the_shown_samples(self):
        prompts = []
        run("fake", [1, 2], 4, [0.0, 0.1], lambda p: prompts.append(p) or "{}", log=lambda _: None)
        expected = [build_prompt(s) for seed in (1, 2) for noise in (0.0, 0.1)
                    for s in shown_population(seed, 4, noise)]
        self.assertEqual(prompts, expected)


class ParseTests(unittest.TestCase):
    SAMPLE = shown_population(1, 1, 0.0)[0]

    def test_a_well_formed_reply_round_trips(self):
        produced = extract(self.SAMPLE, random.Random(0), {})
        found = parse(reply(produced), self.SAMPLE)
        self.assertEqual(found, {p.finding.attribute: p.finding for p in produced})

    def test_malformed_replies_give_no_findings(self):
        for bad in ("", "not json", "[]", '{"findings": 3}', '{"other": []}'):
            self.assertEqual(parse(bad, self.SAMPLE), {}, bad)

    def test_a_bad_entry_is_skipped_and_the_rest_kept(self):
        good = json.loads(reply(extract(self.SAMPLE, random.Random(0), {})))
        good["findings"][0]["claims"][0]["page"] = "two"
        self.assertEqual(len(parse(json.dumps(good), self.SAMPLE)), 3)

    def test_verdict_is_lowercased(self):
        good = json.loads(reply(extract(self.SAMPLE, random.Random(0), {})))
        good["findings"][0]["verdict"] = "PASS"
        self.assertEqual(parse(json.dumps(good), self.SAMPLE)[good["findings"][0]["attribute"]].verdict, "pass")


class ScoreTests(unittest.TestCase):
    N = 12

    def scored(self, noise, rates, silent_fix=0.5):
        ask = fake_model(self.N, 1, noise, rates, silent_fix)
        records = run("fake", [1], self.N, [noise], ask, log=lambda _: None)
        return records, score(records)

    def total(self, results, noise, checker, key):
        return sum(c[key] for c in results[(noise, checker)])

    def test_a_faithful_model_on_clean_pages_is_verified_and_right(self):
        _, r = self.scored(0.0, {})
        for checker in ("trust", "exact", "tiered"):
            self.assertEqual(self.total(r, 0.0, checker, "findings"), 4 * self.N)
            self.assertEqual(self.total(r, 0.0, checker, "verified"), 4 * self.N)
            self.assertEqual(self.total(r, 0.0, checker, "wrong"), 0)

    def test_fabricated_quotes_are_verified_by_trust_and_rejected_by_the_checkers(self):
        _, r = self.scored(0.0, {"fabricated": 1.0})
        self.assertEqual(self.total(r, 0.0, "trust", "rejected"), 0)
        for checker in ("exact", "tiered"):
            self.assertGreater(self.total(r, 0.0, checker, "rejected"), self.N)
            self.assertEqual(self.total(r, 0.0, checker, "verified_wrong"), 0)
        self.assertGreater(self.total(r, 0.0, "tiered", "reason:quote_not_on_page"), self.N)

    def test_a_wrong_verdict_is_caught_by_the_checkers_and_not_by_trust(self):
        _, r = self.scored(0.0, {"verdict_flip": 1.0})
        self.assertEqual(self.total(r, 0.0, "trust", "verified_wrong"), 4 * self.N)
        self.assertEqual(self.total(r, 0.0, "tiered", "reason:verdict_mismatch"), 4 * self.N)

    def test_noise_splits_the_checkers(self):
        _, r = self.scored(0.1, {})
        self.assertGreater(self.total(r, 0.1, "exact", "rejected"), 0)
        self.assertEqual(self.total(r, 0.1, "tiered", "rejected"), 0)
        self.assertGreater(self.total(r, 0.1, "tiered", "weak"), 0)

    def test_failed_calls_count_as_missing_findings(self):
        def broken(prompt):
            raise ConnectionError("no server")

        records = run("fake", [1], 3, [0.0], broken, log=lambda _: None)
        self.assertEqual({r["error"] for r in records}, {"ConnectionError: no server"})
        r = score(records)
        self.assertEqual(self.total(r, 0.0, "tiered", "missing"), 12)
        self.assertEqual(self.total(r, 0.0, "tiered", "findings"), 0)
        render(r, describe(records))

    def test_scoring_reads_only_the_stored_replies(self):
        records, r = self.scored(0.1, {"value_drift": 0.5})
        self.assertEqual(score(json.loads(json.dumps(records))), r)

    def test_the_sample_count_comes_from_the_records_not_from_a_setting(self):
        records, full = self.scored(0.1, {})
        short = score(records[:5])
        self.assertEqual(short[(0.1, "tiered")][0]["expected"], 5 * 4)
        self.assertNotEqual(short, full)

    def test_records_carry_the_model_and_temperature_and_the_header_reads_them(self):
        records, r = self.scored(0.0, {})
        self.assertEqual({(x["model"], x["temperature"]) for x in records}, {("fake", 0)})
        meta = describe(records)
        self.assertEqual(meta, {"models": ["fake"], "temperatures": [0], "seeds": [1], "samples": [self.N]})
        self.assertIn("model fake, seeds [1], samples per seed and noise level [12], temperature 0", render(r, meta))

    def test_the_header_follows_the_records_when_a_run_stopped_early(self):
        records, r = self.scored(0.0, {})
        self.assertEqual(describe(records[:7])["samples"], [7])

    def test_a_reply_that_does_not_name_its_model_gives_a_header_that_says_so(self):
        records, r = self.scored(0.0, {})
        old = [{k: v for k, v in rec.items() if k not in ("model", "temperature")} for rec in records]
        meta = describe(old)
        self.assertEqual((meta["models"], meta["temperatures"]), ([], []))
        header = render(score(old), meta).splitlines()[0]
        self.assertTrue(header.startswith("model not recorded in the replies, seeds [1]"), header)
        self.assertTrue(header.endswith("temperature not recorded in the replies"), header)

    def test_a_second_finding_for_the_same_attribute_is_ignored(self):
        sample = shown_population(1, 1, 0.0)[0]
        produced = extract(sample, random.Random(0), {})
        data = json.loads(reply(produced))
        twice = dict(data, findings=data["findings"] + [dict(data["findings"][0], verdict="exception")])
        found = parse(json.dumps(twice), sample)
        self.assertEqual(found[data["findings"][0]["attribute"]].verdict, data["findings"][0]["verdict"])

    def test_scoring_changes_when_a_stored_reply_changes(self):
        records, full = self.scored(0.0, {})
        blanked = [dict(records[0], content="{}")] + records[1:]
        scored = score(blanked)
        self.assertEqual(sum(c["missing"] for c in scored[(0.0, "tiered")]), 4)
        self.assertNotEqual(scored, full)

    def test_the_pages_digest_follows_the_pages(self):
        quiet, _ = self.scored(0.0, {})
        noisy, _ = self.scored(0.1, {})
        self.assertEqual(pages_digest(quiet), pages_digest(json.loads(json.dumps(quiet))))
        self.assertNotEqual(pages_digest(quiet), pages_digest(noisy))
        self.assertNotEqual(pages_digest(quiet), pages_digest(quiet[:-1]))

    def test_replay_stops_when_the_pages_are_not_the_ones_the_replies_were_collected_on(self):
        records, _ = self.scored(0.0, {})
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw.jsonl"
            raw.write_text("".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                main(["--raw", str(raw), "--replay", "--expect-digest", pages_digest(records)])
                with self.assertRaises(SystemExit):
                    main(["--raw", str(raw), "--replay", "--expect-digest", "0" * 64])

    def test_render_lists_each_checker_and_the_reasons(self):
        records, r = self.scored(0.0, {"fabricated": 1.0})
        text = render(r, describe(records))
        for checker in ("trust", "exact", "tiered"):
            self.assertIn(f"| {checker} |", text)
        self.assertIn("quote_not_on_page", text)

    def test_a_live_run_writes_one_raw_line_per_sample_and_a_table(self):
        ask = fake_model(3, 1, 0.0, {})
        with tempfile.TemporaryDirectory() as d:
            raw = Path(d) / "raw.jsonl"
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                main(["--raw", str(raw), "--seeds", "1", "--n", "3", "--noise", "0"], ask=ask)
            lines = raw.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(lines), 3)
        self.assertEqual(json.loads(lines[0])["sample_id"], "S0001")
        self.assertIn("| tiered |", buf.getvalue())

    def test_replay_from_a_raw_file(self):
        records, r = self.scored(0.0, {})
        with tempfile.TemporaryDirectory() as d:
            raw, out = Path(d) / "raw.jsonl", Path(d) / "table.md"
            raw.write_text("".join(json.dumps(x) + "\n" for x in records), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                main(["--raw", str(raw), "--replay", "--out", str(out)])
            self.assertEqual(out.read_text(encoding="utf-8"), render(r, describe(records)))


class StoredRunTests(unittest.TestCase):
    """The checked-in replies are still scored on the pages they were collected on."""

    RESULTS = Path(__file__).resolve().parent.parent / "results"

    def test_the_stored_replies_hash_to_the_digest_in_the_run_note(self):
        records = [json.loads(line) for line in
                   (self.RESULTS / "qwen3-4b-raw.jsonl").read_text(encoding="utf-8").splitlines() if line]
        note = (self.RESULTS / "qwen3-4b-run.txt").read_text(encoding="utf-8")
        recorded = next(line.split(":", 1)[1].strip() for line in note.splitlines() if line.startswith("pages-sha256:"))
        self.assertEqual(len(records), 120)
        self.assertEqual(pages_digest(records), recorded)

    def test_the_stored_table_is_what_the_stored_replies_score_to(self):
        records = [json.loads(line) for line in
                   (self.RESULTS / "qwen3-4b-raw.jsonl").read_text(encoding="utf-8").splitlines() if line]
        stored = (self.RESULTS / "qwen3-4b.md").read_text(encoding="utf-8")
        self.assertEqual(render(score(records), describe(records)), stored)


if __name__ == "__main__":
    unittest.main()
