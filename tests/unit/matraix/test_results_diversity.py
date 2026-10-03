"""Tests for deterministic response-diversity diagnostics in ``matraix results``."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from matraix import job_results as job_results_module
from matraix.job_results import (
    collect_job_results,
    format_csv_report,
    format_json_report,
    format_text_report,
)
from matraix.results_diversity import (
    LOW_EFFECTIVE_ANSWERS,
    QuestionMeta,
    canonical_answer,
    compute_diversity,
)


_DEGENERATE_RATIONALE = (
    "The product looks useful and I would probably tell my friends about it soon."
)
_DISTINCT_REASONS = [
    "Battery life matters most to me when I travel for work every week.",
    "I care mainly about the camera quality for family photos at home.",
    "Price is the deciding factor because I am saving for a mortgage.",
    "Screen size is what I notice first when comparing phones in a store.",
    "Brand reputation drives my choice since my last phone lasted years.",
    "Storage capacity matters because I record long videos for my channel.",
]


def _answer(qid: str, value, rationale: str = "") -> dict:
    return {"questionId": qid, "value": value, "rationale": rationale}


def _write_trial(job: Path, trial_name: str, answers: list[dict]) -> Path:
    trial = job / trial_name
    output = trial / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    if not (job / "result.json").is_file():
        (job / "result.json").write_text(
            json.dumps({"stats": {"n_completed_trials": 1, "n_errored_trials": 0}}),
            encoding="utf-8",
        )
    (trial / "result.json").write_text(
        json.dumps({"verifier_result": {"rewards": {"reward": 1.0}}}),
        encoding="utf-8",
    )
    (trial / "persona_meta.json").write_text(
        json.dumps({"persona_id": trial_name, "display_name": trial_name}),
        encoding="utf-8",
    )
    (output / "survey_result.json").write_text(
        json.dumps({"answers": answers}),
        encoding="utf-8",
    )
    return trial


def _write_survey_job(
    tmp_path: Path, name: str, per_trial_answers: list[list[dict]]
) -> Path:
    job = tmp_path / "jobs" / name
    for index, answers in enumerate(per_trial_answers):
        _write_trial(job, f"survey_{name}__{index:02d}", answers)
    return job


def _write_chat_job(tmp_path: Path) -> Path:
    job = tmp_path / "jobs" / "demo-chat"
    trial = job / "chat_demo__xyz"
    output = trial / "artifacts" / "app" / "output"
    output.mkdir(parents=True)
    (job / "result.json").write_text(
        json.dumps({"stats": {"n_completed_trials": 1, "n_errored_trials": 0}}),
        encoding="utf-8",
    )
    (trial / "result.json").write_text(
        json.dumps({"verifier_result": {"rewards": {"reward": 1.0}}}),
        encoding="utf-8",
    )
    (trial / "persona_meta.json").write_text(
        json.dumps({"persona_id": "xyz", "display_name": "Chat Persona"}),
        encoding="utf-8",
    )
    verifier = trial / "verifier"
    verifier.mkdir(parents=True)
    (verifier / "structured_output.json").write_text(
        json.dumps(
            {
                "taskType": "chatbot",
                "contexts": [
                    {
                        "contextType": "task_outcome",
                        "key": "task_outcome.primary",
                        "facets": [{"key": "outcome_status", "value": "passed"}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return job


def _write_trial_with_meta(
    job: Path,
    trial_name: str,
    answers: list[dict],
    *,
    question_meta: dict | None = None,
) -> Path:
    """Write a trial whose structured output mirrors the artifact answers.

    ``question_meta`` is merged into each question_response context so the
    verifier carries questionnaire metadata (questionType / scale bounds).
    """
    trial = _write_trial(job, trial_name, answers)
    if question_meta:
        verifier = trial / "verifier"
        verifier.mkdir(parents=True, exist_ok=True)
        contexts = []
        for answer in answers:
            contexts.append(
                {
                    "contextType": "question_response",
                    "key": f"question.{answer['questionId']}",
                    **question_meta,
                    "facets": [
                        {"key": "response", "value": answer["value"]},
                        {"key": "reason", "value": answer["rationale"]},
                    ],
                }
            )
        (verifier / "structured_output.json").write_text(
            json.dumps({"taskType": "survey", "contexts": contexts}),
            encoding="utf-8",
        )
    return trial


def _degenerate_answers(index: int) -> list[dict]:
    rationale = _DEGENERATE_RATIONALE + (" Thanks!" if index % 2 else "")
    return [
        _answer("q_interest", 4, rationale),
        _answer("q_price", 3, rationale),
    ]


def _degenerate_job(tmp_path: Path) -> Path:
    return _write_survey_job(
        tmp_path, "degenerate", [_degenerate_answers(index) for index in range(6)]
    )


def test_degenerate_job_flags_low(tmp_path: Path) -> None:
    report = collect_job_results(_degenerate_job(tmp_path))
    assert report.app_type == "survey"
    diversity = report.lens.diversity
    assert diversity is not None
    assert diversity.method == "deterministic-v1"
    assert diversity.evaluated == 2
    assert diversity.flagged_low == 2
    assert diversity.flagged_moderate == 0
    for entry in diversity.questions:
        assert entry.status == "evaluated"
        assert entry.flag == "low"
        assert entry.n == 6
        assert entry.top_share == 1.0
        assert entry.effective_answers == pytest.approx(1.0)
        assert entry.pair_match_rate == 1.0
        assert entry.rationale_dup_rate == 1.0


def test_diverse_job_is_ok(tmp_path: Path) -> None:
    per_trial = [
        [_answer("q_interest", value, _DISTINCT_REASONS[index])]
        for index, value in enumerate([1, 2, 3, 4, 5, 4])
    ]
    report = collect_job_results(_write_survey_job(tmp_path, "diverse", per_trial))
    diversity = report.lens.diversity
    assert diversity is not None
    entry = diversity.questions[0]
    assert entry.status == "evaluated"
    assert entry.flag == "ok"
    assert entry.n == 6
    assert entry.top_share == pytest.approx(2 / 6, abs=1e-3)
    assert entry.effective_answers > 2.0
    assert entry.pair_match_rate < 0.5
    assert entry.rationale_dup_rate == 0.0
    assert diversity.flagged_low == 0
    assert diversity.flagged_moderate == 0


def test_fewer_than_three_answers_skipped(tmp_path: Path) -> None:
    per_trial = [
        [_answer("q_interest", 4, "Short shared reason one.")],
        [_answer("q_interest", 4, "Short shared reason two.")],
    ]
    report = collect_job_results(_write_survey_job(tmp_path, "tiny", per_trial))
    diversity = report.lens.diversity
    assert diversity is not None
    assert diversity.evaluated == 0
    assert diversity.flagged_low == 0
    entry = diversity.questions[0]
    assert entry.n == 2
    assert entry.status == "skipped"
    assert entry.flag is None


def test_small_n_moderate_suppressed_but_low_not(tmp_path: Path) -> None:
    per_trial: list[list[dict]] = []
    for index in range(6):
        row = [_answer("q_big", 4 if index < 4 else 2, _DISTINCT_REASONS[index])]
        if index < 4:
            row.append(
                _answer("q_small", 4 if index < 3 else 2, _DISTINCT_REASONS[index])
            )
        per_trial.append(row)
    report = collect_job_results(_write_survey_job(tmp_path, "smalln", per_trial))
    diversity = report.lens.diversity
    assert diversity is not None
    entries = {entry.question_id: entry for entry in diversity.questions}
    # n=4 with top=0.75 / eff<=2.0: MODERATE suppressed by the small-n rule.
    small = entries["q_small"]
    assert small.n == 4
    assert small.top_share == pytest.approx(0.75, abs=1e-3)
    assert small.effective_answers <= 2.0
    assert small.flag == "ok"
    # Same shape at n=6: MODERATE fires.
    big = entries["q_big"]
    assert big.n == 6
    assert big.top_share == pytest.approx(4 / 6, abs=1e-3)
    assert big.effective_answers <= 2.0
    assert big.flag == "moderate"
    assert diversity.flagged_moderate == 1
    assert diversity.flagged_low == 0


def test_rationale_dup_rate_upgrades_to_low(tmp_path: Path) -> None:
    per_trial = [
        [_answer("q_like", value, _DEGENERATE_RATIONALE)]
        for value in [1, 2, 3, 4, 5, 5]
    ]
    report = collect_job_results(_write_survey_job(tmp_path, "duprate", per_trial))
    diversity = report.lens.diversity
    assert diversity is not None
    entry = diversity.questions[0]
    # Spread answers alone would be ok; near-identical rationales upgrade LOW.
    assert entry.top_share < 0.80
    assert entry.effective_answers > LOW_EFFECTIVE_ANSWERS
    assert entry.rationale_dup_rate == 1.0
    assert entry.flag == "low"
    assert diversity.flagged_low == 1


def test_json_round_trip_diversity_block(tmp_path: Path) -> None:
    payload = json.loads(
        format_json_report(collect_job_results(_degenerate_job(tmp_path)))
    )
    block = payload["lens"]["diversity"]
    assert block["method"] == "deterministic-v1"
    assert block["evaluated"] == 2
    assert block["flaggedLow"] == 2
    assert block["flaggedModerate"] == 0
    assert len(block["questions"]) == 2
    entry = block["questions"][0]
    assert set(entry) == {
        "questionId",
        "n",
        "topShare",
        "normEntropy",
        "effectiveAnswers",
        "pairMatchRate",
        "rationaleDupRate",
        "categoryCount",
        "flag",
        "status",
    }
    for key in (
        "topShare",
        "normEntropy",
        "effectiveAnswers",
        "pairMatchRate",
        "rationaleDupRate",
        "categoryCount",
    ):
        assert entry[key] == round(entry[key], 3)
    assert entry["flag"] == "low"
    assert entry["status"] == "evaluated"
    # No questionnaire metadata for this job: K falls back to n (6 trials).
    assert entry["categoryCount"] == 6.0


def test_text_report_includes_diversity_section(tmp_path: Path) -> None:
    text = format_text_report(collect_job_results(_degenerate_job(tmp_path)))
    assert "Response diversity" in text
    assert (
        "Diversity: 2 of 2 questions flagged LOW - responses may be "
        "model-dominated (deterministic-v1)" in text
    )
    row = next(
        line for line in text.splitlines() if line.strip().startswith("q_interest")
    )
    assert "n=6" in row
    assert "top=1.000" in row
    assert "dup=1.000" in row
    assert row.rstrip().endswith("low")


def test_chat_job_has_no_diversity(tmp_path: Path) -> None:
    report = collect_job_results(_write_chat_job(tmp_path))
    assert report.app_type == "chatbot"
    assert report.lens is not None
    assert report.lens.diversity is None
    assert "Response diversity" not in format_text_report(report)
    payload = json.loads(format_json_report(report))
    assert payload["lens"]["diversity"] is None


def test_two_collects_produce_identical_payload(tmp_path: Path) -> None:
    job = _degenerate_job(tmp_path)
    first = collect_job_results(job).to_dict()
    second = collect_job_results(job).to_dict()
    first.pop("generatedAt")
    second.pop("generatedAt")
    assert first == second


def test_csv_and_ledger_outputs_unchanged_by_rationales(tmp_path: Path) -> None:
    report = collect_job_results(_degenerate_job(tmp_path))
    header = format_csv_report(report).splitlines()[0]
    assert "rationale" not in header
    payload = json.loads(format_json_report(report))
    trial_row = payload["ledger"]["trials"][0]
    assert set(trial_row) == {
        "trial_name",
        "persona_id",
        "persona_name",
        "reward",
        "error",
        "usage",
        "artifact_paths",
        "signals",
        "group_values",
        "survey_answers",
    }


def test_likert_scale_metadata_normalizes_entropy(tmp_path: Path) -> None:
    job = tmp_path / "jobs" / "scaled"
    for index, value in enumerate([1, 2, 3, 4, 5, 4]):
        answers = [_answer("q_scale", value, _DISTINCT_REASONS[index])]
        _write_trial_with_meta(
            job,
            f"scaled__{index:02d}",
            answers,
            question_meta={"questionType": "likert", "scaleMin": 1, "scaleMax": 5},
        )
    report = collect_job_results(job)
    assert report.lens is not None and report.lens.diversity is not None
    entry = report.lens.diversity.questions[0]
    assert entry.n == 6
    assert entry.category_count == pytest.approx(5.0)
    assert entry.norm_entropy <= 1.0
    assert not any("K=ln(n) fallback" in note for note in report.notes)


def test_likert_without_scale_uses_default_k5(tmp_path: Path) -> None:
    """Likert with no scale metadata normalizes with the product default 1-5."""
    job = tmp_path / "jobs" / "likert-default"
    for index, value in enumerate([1, 2, 3, 4, 5, 4]):
        _write_trial_with_meta(
            job,
            f"likertdef__{index:02d}",
            [_answer("q_likert", value, _DISTINCT_REASONS[index])],
            question_meta={"questionType": "likert"},
        )
    report = collect_job_results(job)
    assert report.lens is not None and report.lens.diversity is not None
    entry = report.lens.diversity.questions[0]
    assert entry.category_count == pytest.approx(5.0)
    payload = json.loads(format_json_report(report))
    assert payload["lens"]["diversity"]["questions"][0]["categoryCount"] == 5.0


def test_unknown_categories_use_n_basis_without_note(tmp_path: Path) -> None:
    """No questionnaire -> K = n; the per-run fallback note is gone for good."""
    per_trial = [
        [_answer("q_interest", value, _DISTINCT_REASONS[index])]
        for index, value in enumerate([1, 2, 3, 4, 5, 4])
    ]
    report = collect_job_results(_write_survey_job(tmp_path, "nometa", per_trial))
    assert report.lens is not None and report.lens.diversity is not None
    assert not any("K=ln(n)" in note for note in report.notes)
    entry = report.lens.diversity.questions[0]
    assert entry.category_count == pytest.approx(6.0)
    assert 0.0 < entry.norm_entropy <= 1.0


def test_compute_diversity_direct_with_category_count() -> None:
    rows = [(value, f"reason {value} text") for value in range(1, 6)]
    known = compute_diversity(
        {"q": rows},
        question_meta={"q": QuestionMeta(question_type="likert", category_count=5)},
    )
    fallback = compute_diversity({"q": rows})
    entry = known.questions[0]
    assert entry.n == 5
    assert entry.top_share == pytest.approx(0.2)
    assert entry.effective_answers == pytest.approx(5.0)
    assert entry.norm_entropy == pytest.approx(1.0)
    # Fallback K is n (5 distinct answers here), so it matches explicit K=5.
    assert fallback.questions[0].category_count == pytest.approx(5.0)
    assert fallback.questions[0].norm_entropy == entry.norm_entropy
    assert entry.flag == "ok"


def test_ten_distinct_answers_normalize_to_one() -> None:
    """CRIT regression: K=n fallback gives H/ln(n); 10 distinct answers -> 1.0."""
    rationales = [
        "Battery endurance decides my phone purchases every single time.",
        "I pick whichever camera shoots the best low-light family photos.",
        "The price has to fit a strict monthly budget or I walk away.",
        "Screen brightness outdoors is the feature I care about most.",
        "Brand trust built over years is what keeps me loyal here.",
        "Storage for offline videos is my number one requirement.",
        "Fast charging matters because my days are unpredictable.",
        "A replaceable battery wins me over more than slim design.",
        "Software update promises decide which phone I will buy.",
        "Durability after drops is the test I put every phone through.",
    ]
    rows = [(value, rationales[value - 1]) for value in range(1, 11)]
    entry = compute_diversity({"q": rows}).questions[0]
    assert entry.n == 10
    assert entry.top_share == pytest.approx(0.1)
    assert entry.effective_answers == pytest.approx(10.0)
    assert entry.category_count == pytest.approx(10.0)
    assert round(entry.norm_entropy, 3) == 1.0
    assert entry.to_dict()["normEntropy"] == 1.0
    assert entry.rationale_dup_rate == 0.0
    assert entry.flag == "ok"


def test_multi_choice_sets_collapse_regardless_of_order() -> None:
    """CRIT regression: multi_choice lists are order-insensitive sets."""
    rows = [
        (["a", "b"], _DISTINCT_REASONS[0]),
        (["b", "a"], _DISTINCT_REASONS[1]),
        (["a", "b"], _DISTINCT_REASONS[2]),
        (["b", "a"], _DISTINCT_REASONS[3]),
    ]
    entry = compute_diversity({"q": rows}).questions[0]
    assert entry.n == 4
    assert entry.top_share == 1.0
    assert entry.effective_answers == pytest.approx(1.0)
    assert entry.flag == "low"
    # Scalar behavior stays byte-identical to plain str(value).
    assert canonical_answer("plain") == "plain"
    assert canonical_answer(4) == "4"


def test_multi_choice_order_insensitive_end_to_end(tmp_path: Path) -> None:
    per_trial = [
        [_answer("q_features", ["price", "camera"], _DISTINCT_REASONS[0])],
        [_answer("q_features", ["camera", "price"], _DISTINCT_REASONS[1])],
        [_answer("q_features", ["price", "camera"], _DISTINCT_REASONS[2])],
    ]
    report = collect_job_results(_write_survey_job(tmp_path, "multichoice", per_trial))
    diversity = report.lens.diversity
    assert diversity is not None
    entry = diversity.questions[0]
    assert entry.n == 3
    assert entry.top_share == 1.0
    assert entry.effective_answers == pytest.approx(1.0)
    assert entry.pair_match_rate == 1.0
    assert entry.flag == "low"
    # Distribution counting is order-insensitive too (_count_signal).
    assert report.question_distributions["q_features"] == {"('camera', 'price')": 3}


def test_rationale_dup_low_requires_two_pairs() -> None:
    """One duplicated pair at n=3 gives rate 1/3 but must not flag LOW."""
    rationale_a = "Battery life is the one specification I check before anything else."
    rationale_b = "Camera quality matters more to me than any other phone feature."
    one_pair = compute_diversity(
        {"q": [(1, rationale_a), (2, rationale_a), (3, rationale_b)]}
    ).questions[0]
    assert one_pair.rationale_dup_rate == pytest.approx(1 / 3)
    assert one_pair.flag == "ok"
    two_pairs = compute_diversity(
        {
            "q": [
                (1, rationale_a),
                (2, rationale_a),
                (3, rationale_b),
                (4, rationale_b),
            ]
        }
    ).questions[0]
    assert two_pairs.rationale_dup_rate == pytest.approx(1 / 3)
    assert two_pairs.flag == "low"


def test_dup_pairs_exclude_rows_without_answer_value() -> None:
    """Rationales from value-None rows stay out of the dup population."""
    rows = [
        (1, _DISTINCT_REASONS[0]),
        (2, _DISTINCT_REASONS[1]),
        (3, _DISTINCT_REASONS[2]),
        (None, _DISTINCT_REASONS[0]),
    ]
    entry = compute_diversity({"q": rows}).questions[0]
    assert entry.n == 3
    assert entry.rationale_dup_rate == 0.0
    assert entry.flag == "ok"


def test_short_identical_rationales_count_as_dups() -> None:
    """Exact-string fast path catches texts shorter than the shingle width."""
    rows = [(1, "meh"), (2, "meh"), (3, _DISTINCT_REASONS[0])]
    entry = compute_diversity({"q": rows}).questions[0]
    assert entry.rationale_dup_rate == pytest.approx(1 / 3)
    assert entry.flag == "ok"
    all_same = compute_diversity({"q": [(1, "meh"), (2, "meh"), (3, "meh")]}).questions[
        0
    ]
    assert all_same.rationale_dup_rate == 1.0
    assert all_same.flag == "low"


def test_dup_rate_grouped_and_fast_for_many_personas() -> None:
    """200 personas over 3 exact texts: no pairwise blowup, exact dup rate."""
    texts = _DISTINCT_REASONS[:3]
    rows = [(index % 5 + 1, texts[index % 3]) for index in range(200)]
    start = time.perf_counter()
    entry = compute_diversity({"q": rows}).questions[0]
    elapsed = time.perf_counter() - start
    group_sizes = [67, 67, 66]
    expected_rate = sum(size * (size - 1) // 2 for size in group_sizes) / (
        200 * 199 // 2
    )
    assert entry.rationale_dup_rate == pytest.approx(expected_rate)
    # Rate 1/3 >= 0.30 across thousands of duplicated pairs: LOW is correct.
    assert entry.flag == "low"
    assert elapsed < 2.0


def test_lens_json_keys_pinned(tmp_path: Path) -> None:
    """Serializer parity: hand-built lens dict must not silently drop fields."""
    payload = json.loads(
        format_json_report(collect_job_results(_degenerate_job(tmp_path)))
    )
    assert set(payload["lens"]) == {
        "kind",
        "primarySummary",
        "distributions",
        "metrics",
        "source",
        "diversity",
    }


def test_structured_output_read_once_per_trial(tmp_path: Path, monkeypatch) -> None:
    """Question meta is threaded from _summarize_trial: one read per trial."""
    job = tmp_path / "jobs" / "oneread"
    for index, value in enumerate([1, 2, 3, 4]):
        _write_trial_with_meta(
            job,
            f"oneread__{index:02d}",
            [_answer("q_scale", value, _DISTINCT_REASONS[index])],
            question_meta={"questionType": "likert", "scaleMin": 1, "scaleMax": 5},
        )
    original = job_results_module._structured_output
    calls = {"count": 0}

    def counting(trial_dir: Path):
        calls["count"] += 1
        return original(trial_dir)

    monkeypatch.setattr(job_results_module, "_structured_output", counting)
    report = collect_job_results(job)
    assert report.app_type == "survey"
    assert calls["count"] == 4  # exactly one structured-output read per trial
    diversity = report.lens.diversity
    assert diversity is not None
    assert diversity.questions[0].category_count == pytest.approx(5.0)
