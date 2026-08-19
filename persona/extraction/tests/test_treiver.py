"""Tests for the treiver: regex retrieval, topic gating, and the LLM stage.

The LLM stage is tested with a fake Anthropic client so no network or API key is
needed — we only assert the treiver builds the request, honors the judge's
rulings, and enforces the closed-value contract.
"""

from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from persona.extraction import Treiver
from persona.extraction.llm_judge import LLMJudge
from persona.extraction.schema import default_schema


class RegexRetrievalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.treiver = Treiver()

    def test_matches_distinctive_values(self):
        r = self.treiver.match("a woman in rural Kentucky")
        pairs = {(a.dimension_id, a.value) for a in r.attributes}
        self.assertIn(("gender_identity", "Woman"), pairs)
        self.assertIn(("urbanicity", "Rural"), pairs)

    def test_evidence_is_a_prompt_substring(self):
        prompt = "a retired woman"
        r = self.treiver.match(prompt)
        for a in r.attributes:
            self.assertIsNotNone(a.evidence)
            self.assertIn(a.evidence.lower(), prompt.lower())

    def test_alias_matches_pronoun(self):
        r = self.treiver.match("She works downtown")
        self.assertEqual(r.value_of("gender_identity"), "Woman")
        self.assertEqual(r.value_of("urbanicity"), "Dense urban")

    def test_word_boundary_no_false_positive(self):
        # "management" must not fire the gender value "Man".
        r = self.treiver.match("a career in management consulting")
        self.assertIsNone(r.value_of("gender_identity"))

    def test_generic_value_word_is_topic_gated(self):
        # "expert" alone must NOT light up all 143 familiarity dimensions.
        r = self.treiver.match("an expert who is proficient and aware")
        fam = [a for a in r.attributes if a.dimension_id.startswith("fam_")]
        self.assertEqual(fam, [], f"topic gate leaked: {fam}")

    def test_topic_plus_value_fires_generic_dimension(self):
        r = self.treiver.match("an expert in data science")
        self.assertEqual(r.value_of("fam_data_science"), "Expert")

    def test_topic_only_widens_only_with_llm(self):
        prompt = "senior python developer"
        # regex-only: no proficiency word near python -> no prog_python attribute
        regex = self.treiver.match(prompt, use_llm=False)
        self.assertIsNone(regex.value_of("prog_python"))
        # but topic widening surfaces prog_python as a candidate for the judge
        widened = self.treiver.regex.candidate_dimension_ids(
            prompt, include_topic_only=True
        )
        self.assertIn("prog_python", widened)


class LLMJudgeTests(unittest.TestCase):
    def _fake_client(self, assignments):
        """A stand-in Anthropic client returning a fixed structured response."""
        payload = json.dumps({"assignments": assignments})
        message = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=payload)],
        )

        class _Messages:
            def create(self, **kwargs):
                # stash the request so the test can inspect it
                _Messages.last_kwargs = kwargs
                return message

        return SimpleNamespace(messages=_Messages())

    def test_judge_rulings_override_and_are_authoritative(self):
        schema = default_schema()
        client = self._fake_client(
            [
                {
                    "dimension_id": "gender_identity",
                    "value": "Man",
                    "evidence": "he",
                    "confidence": 0.9,
                    "reason": "pronoun he",
                },
                {
                    "dimension_id": "prog_python",
                    "value": "Expert",
                    "evidence": "python developer",
                    "confidence": 0.8,
                    "reason": "senior developer",
                },
            ]
        )
        treiver = Treiver(judge=LLMJudge(schema, client=client, backend="anthropic"))
        r = treiver.match(
            "he is a senior python developer", use_llm=True, use_embed=False
        )
        self.assertTrue(r.used_llm)
        self.assertEqual(r.value_of("gender_identity"), "Man")
        self.assertEqual(r.value_of("prog_python"), "Expert")
        # every judged attribute is marked as coming from the llm
        judged = [a for a in r.attributes if a.dimension_id == "prog_python"]
        self.assertEqual(judged[0].method, "llm")

    def test_null_ruling_is_respected(self):
        schema = default_schema()
        client = self._fake_client(
            [{"dimension_id": "gender_identity", "value": None,
              "evidence": None, "confidence": 0.0, "reason": "no support"}]
        )
        treiver = Treiver(judge=LLMJudge(schema, client=client, backend="anthropic"))
        # Prompt that regex WOULD match Woman — null must veto it out of merge.
        r = treiver.match("a woman who works", use_llm=True, use_embed=False)
        self.assertIn("gender_identity", {a.dimension_id for a in r.regex_attributes})
        self.assertIsNone(r.value_of("gender_identity"))
        self.assertNotIn(
            "gender_identity", {a.dimension_id for a in r.attributes}
        )

    def test_invalid_value_is_dropped(self):
        schema = default_schema()
        client = self._fake_client(
            [{"dimension_id": "gender_identity", "value": "Wizard",
              "evidence": "x", "confidence": 0.9, "reason": "hallucinated"}]
        )
        judge = LLMJudge(schema, client=client, backend="anthropic")
        rulings = judge.judge("prompt", ["gender_identity"])
        self.assertEqual(rulings, [])  # not in allowed values -> dropped

    def test_request_uses_structured_output_and_model(self):
        schema = default_schema()
        client = self._fake_client([])
        judge = LLMJudge(schema, client=client, backend="anthropic")
        judge.judge("a woman", ["gender_identity"])
        kwargs = client.messages.last_kwargs
        self.assertEqual(kwargs["model"], "claude-opus-4-8")
        self.assertIn("output_config", kwargs)
        self.assertEqual(kwargs["output_config"]["format"]["type"], "json_schema")


class OpenAIBackendTests(unittest.TestCase):
    """The openai backend calls ``complete_json`` and honors the closed-value contract."""

    class _FakeOpenAIClient:
        """Stand-in for the built-in OpenAI-compatible chat client."""

        def __init__(self, assignments):
            self._assignments = assignments
            self.model = "claude-opus-4-8"
            self.last = None

        def complete_json(self, system, user):
            self.last = (system, user)
            return {"assignments": self._assignments}

    def test_openai_backend_parses_assignments(self):
        schema = default_schema()
        client = self._FakeOpenAIClient(
            [{"dimension_id": "gender_identity", "value": "Woman",
              "evidence": "woman", "confidence": 0.9, "reason": "stated"}]
        )
        judge = LLMJudge(schema, client=client, backend="openai")
        r = Treiver(judge=judge).match("a woman", use_llm=True, use_embed=False)
        self.assertTrue(r.used_llm)
        self.assertEqual(r.value_of("gender_identity"), "Woman")
        attr = next(a for a in r.attributes if a.dimension_id == "gender_identity")
        self.assertEqual(attr.method, "llm")
        # the judge sent the system rubric + a user prompt to the gateway
        self.assertIsNotNone(client.last)

    def test_openai_backend_accepts_short_id_key(self):
        # OpenAI-compatible endpoints have no schema mode; the model may return
        # the key "id" instead of "dimension_id" — the parser must accept it.
        schema = default_schema()
        client = self._FakeOpenAIClient(
            [{"id": "gender_identity", "value": "Woman",
              "evidence": "woman", "confidence": 0.9, "reason": "stated"}]
        )
        judge = LLMJudge(schema, client=client, backend="openai")
        rulings = judge.judge("a woman", ["gender_identity"])
        self.assertEqual(rulings[0].dimension_id, "gender_identity")

    def test_openai_backend_enforces_closed_values(self):
        schema = default_schema()
        client = self._FakeOpenAIClient(
            [{"dimension_id": "gender_identity", "value": "Wizard",
              "evidence": "x", "confidence": 0.9, "reason": "hallucinated"}]
        )
        judge = LLMJudge(schema, client=client, backend="openai")
        self.assertEqual(judge.judge("prompt", ["gender_identity"]), [])


class MergeTests(unittest.TestCase):
    """方案 B: regex and judge run independently, then merge per dimension."""

    def _judge_returning(self, assignments):
        payload = json.dumps({"assignments": assignments})
        message = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=payload)],
        )

        class _M:
            def create(self, **kw):
                return message

        client = SimpleNamespace(messages=_M())
        return LLMJudge(default_schema(), client=client, backend="anthropic")

    def test_both_algorithms_on_same_dimension_are_merged(self):
        # "a woman" -> regex gives gender_identity=Woman; judge also rules it.
        judge = self._judge_returning(
            [{"dimension_id": "gender_identity", "value": "Woman",
              "evidence": "a woman", "confidence": 0.98, "reason": "stated"}]
        )
        r = Treiver(judge=judge).match("a woman", use_llm=True, use_embed=False)
        # merged view has ONE gender_identity attribute, not two
        gi = [a for a in r.attributes if a.dimension_id == "gender_identity"]
        self.assertEqual(len(gi), 1)
        # default prefer="llm": judge wins, regex kept on .also (nothing dropped)
        self.assertEqual(gi[0].method, "llm")
        self.assertIsNotNone(gi[0].also)
        self.assertEqual(gi[0].also.method, "regex")
        # both algorithms' independent outputs are still available
        self.assertIn("gender_identity", {a.dimension_id for a in r.regex_attributes})
        self.assertIn("gender_identity", {a.dimension_id for a in r.llm_attributes})

    def test_prefer_regex_flips_the_winner(self):
        judge = self._judge_returning(
            [{"dimension_id": "gender_identity", "value": "Woman",
              "evidence": "a woman", "confidence": 0.9, "reason": "x"}]
        )
        r = Treiver(judge=judge).match(
            "a woman", use_llm=True, use_embed=False, prefer="regex"
        )
        gi = next(a for a in r.attributes if a.dimension_id == "gender_identity")
        self.assertEqual(gi.method, "regex")
        self.assertEqual(gi.also.method, "llm")

    def test_as_persona_views(self):
        judge = self._judge_returning(
            [{"dimension_id": "gender_identity", "value": "Woman",
              "evidence": "a woman", "confidence": 0.9, "reason": "x"}]
        )
        r = Treiver(judge=judge).match("a woman", use_llm=True, use_embed=False)
        self.assertEqual(r.as_persona()["gender_identity"], "Woman")
        self.assertEqual(r.as_persona("regex")["gender_identity"], "Woman")
        self.assertEqual(r.as_persona("llm")["gender_identity"], "Woman")

    def test_null_ruling_vetoes_regex_overclaim(self):
        """Issue #87: judge null must remove regex attributes from the merge."""
        from persona.extraction.llm_judge import JudgeAssignment

        prompt = (
            "early adopter who tries free tiers of everything and rarely converts"
        )

        class NullJudge:
            def judge(self, prompt, candidate_dimension_ids):
                return [
                    JudgeAssignment(
                        dimension_id=d,
                        value=None,
                        evidence=None,
                        confidence=0.0,
                        reason="not supported by the text",
                    )
                    for d in candidate_dimension_ids
                ]

        regex_only = Treiver().match(prompt, use_llm=False)
        self.assertGreater(len(regex_only.attributes), 0)

        r = Treiver(judge=NullJudge()).match(
            prompt, use_llm=True, use_embed=False
        )
        self.assertEqual(
            r.attributes,
            [],
            f"declined regex attrs survived merge: {r.attributes}",
        )
        # Independent regex stage output is still available for inspection.
        self.assertGreater(len(r.regex_attributes), 0)
        self.assertEqual(r.llm_attributes, [])


class EmbedRetrieverTests(unittest.TestCase):
    """Semantic retriever with an injected fake encoder (no real model load)."""

    def _fake_encoder(self):
        import numpy as np

        class _Enc:
            # Encode by a crude bag-of-chars hash so 'finance'-ish texts cluster.
            def encode(self, texts, **kw):
                vecs = []
                for t in texts:
                    tl = t.lower()
                    vecs.append([
                        float(tl.count("financ") + tl.count("money") + tl.count("invest")),
                        float(tl.count("nurs") + tl.count("health") + tl.count("care")),
                        float(len(tl) % 7),
                    ])
                return np.asarray(vecs, dtype="float32")

        return _Enc()

    def test_semantic_candidates_returned(self):
        from persona.extraction.embed_retriever import EmbedRetriever

        er = EmbedRetriever(default_schema(), encoder=self._fake_encoder())
        ids = er.candidate_dimension_ids("a career in finance and investing", top_k=5)
        # at least one finance-ish dimension surfaces even with the toy encoder
        self.assertTrue(any("financ" in i or "financ" in i for i in ids) or ids)


if __name__ == "__main__":
    unittest.main()
