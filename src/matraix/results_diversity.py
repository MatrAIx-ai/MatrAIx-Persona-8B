"""Deterministic response-diversity diagnostics for ``matraix results``.

Pure stdlib math over per-question ``(answer value, rationale text)`` pairs
already collected from the job tree. No LLM calls, no numpy/pandas; identical
inputs always produce identical output (``method="deterministic-v1"``).

Detects the "one underlying LLM repeating itself" failure mode: many synthetic
personas giving near-identical answers and/or near-identical rationales.
"""

from __future__ import annotations

import itertools
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

# Flag thresholds. LOW = strong evidence of model-dominated responses;
# MODERATE = weak concentration that may still be small-sample noise.
LOW_TOP_SHARE = 0.80
LOW_EFFECTIVE_ANSWERS = 1.5
LOW_RATIONALE_DUP_RATE = 0.30
# The rationale-dup LOW clause also needs at least this many duplicated pairs
# so one chance duplicate among 3 answers (rate 1/3 >= 0.30) cannot flag LOW.
MIN_RATIONALE_DUP_PAIRS_FOR_LOW = 2
MODERATE_TOP_SHARE = 0.60
MODERATE_EFFECTIVE_ANSWERS = 2.0
# n below this: status "skipped", no flag (too few answers to judge).
MIN_EVAL_N = 3
# n in [MIN_EVAL_N, MODERATE_SUPPRESS_MAX_N]: suppress MODERATE (by-chance
# agreement is likely at tiny n); LOW still fires.
MODERATE_SUPPRESS_MAX_N = 5
# Shingle-Jaccard at or above this counts a rationale pair as duplicated.
RATIONALE_DUP_JACCARD = 0.70
# Pairs whose shingle-set size ratio falls below this can never reach
# RATIONALE_DUP_JACCARD, so they are skipped without computing Jaccard.
MIN_JACCARD_LENGTH_RATIO = 0.70
# Character n-gram width for rationale shingles.
SHINGLE_SIZE = 4
# Likert questions without scale metadata normalize with the product default
# 1-5 scale (application/playground/backend/service/survey_types.py).
DEFAULT_LIKERT_K = 5.0


@dataclass(frozen=True)
class QuestionMeta:
    """Optional questionnaire metadata used to normalize entropy.

    ``category_count`` is K (likert: max-min+1; choice: len(options)). When
    unknown, likert questions normalize with the product default K = 5
    (1-5 scale) and everything else with K = n; the K actually used is
    reported per question as ``QuestionDiversity.category_count``.
    """

    question_type: str | None = None
    category_count: int | None = None


@dataclass(frozen=True)
class QuestionDiversity:
    """Per-question diversity metrics and flag."""

    question_id: str
    n: int
    top_share: float
    norm_entropy: float
    effective_answers: float
    pair_match_rate: float
    rationale_dup_rate: float | None
    flag: str | None  # "low" | "moderate" | "ok" | None (skipped)
    status: str  # "evaluated" | "skipped"
    # K actually used to normalize entropy (None when n < 2 and type unknown).
    category_count: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "questionId": self.question_id,
            "n": self.n,
            "topShare": round(self.top_share, 3),
            "normEntropy": round(self.norm_entropy, 3),
            "effectiveAnswers": round(self.effective_answers, 3),
            "pairMatchRate": round(self.pair_match_rate, 3),
            "rationaleDupRate": (
                None
                if self.rationale_dup_rate is None
                else round(self.rationale_dup_rate, 3)
            ),
            "categoryCount": (
                None if self.category_count is None else round(self.category_count, 3)
            ),
            "flag": self.flag,
            "status": self.status,
        }


@dataclass(frozen=True)
class DiversitySummary:
    """Diversity diagnostics across all survey questions of one job."""

    questions: list[QuestionDiversity] = field(default_factory=list)
    method: str = "deterministic-v1"

    @property
    def evaluated(self) -> int:
        return sum(1 for entry in self.questions if entry.status == "evaluated")

    @property
    def flagged_low(self) -> int:
        return sum(1 for entry in self.questions if entry.flag == "low")

    @property
    def flagged_moderate(self) -> int:
        return sum(1 for entry in self.questions if entry.flag == "moderate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "evaluated": self.evaluated,
            "flaggedLow": self.flagged_low,
            "flaggedModerate": self.flagged_moderate,
            "questions": [entry.to_dict() for entry in self.questions],
        }


def _question_sort_key(qid: str) -> tuple[int, int | str]:
    if qid.startswith("q") and qid[1:].isdigit():
        return (0, int(qid[1:]))
    return (1, qid)


def _normalize_text(text: str) -> str:
    """Casefolded, whitespace-collapsed text (NFKC first)."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(normalized.split())


def _shingles(text: str) -> frozenset[str]:
    """Casefolded, whitespace-normalized character 4-grams (NFKC first)."""
    normalized = _normalize_text(text)
    width = SHINGLE_SIZE
    if len(normalized) < width:
        return frozenset()
    return frozenset(
        normalized[index : index + width]
        for index in range(len(normalized) - width + 1)
    )


def canonical_answer(value: Any) -> str:
    """Stable string key for counting answer values.

    List/tuple values (multi_choice answers are lists per
    ``survey_types.SurveyAnswer``) are sorted first so option order cannot
    split identical answer sets across buckets; scalar behavior is unchanged
    (plain ``str(value)``).
    """
    if isinstance(value, (list, tuple)):
        return str(tuple(sorted(value)))
    return str(value)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def _rationale_dup_stats(rationales: Sequence[str]) -> tuple[float, int] | None:
    """Fraction and count of rationale pairs counted as duplicated.

    Rationales are normalized once and grouped by exact normalized string;
    pairs inside one group are duplicates without running Jaccard (this also
    covers short texts below the shingle width, e.g. "meh" vs "meh"). Only
    pairs of DISTINCT normalized strings reach Jaccard, and only when their
    shingle-set size ratio is >= ``MIN_JACCARD_LENGTH_RATIO`` (Jaccard of
    char-k-gram sets is bounded by that ratio, so smaller pairs cannot be
    duplicates).

    Returns None when fewer than 2 non-empty rationales are available.
    """
    normalized: list[str] = []
    for text in rationales:
        if not isinstance(text, str):
            continue
        cleaned = _normalize_text(text)
        if cleaned:
            normalized.append(cleaned)
    rows = len(normalized)
    if rows < 2:
        return None
    group_sizes: Counter[str] = Counter(normalized)
    group_shingles = {text: _shingles(text) for text in sorted(group_sizes)}
    dup_count = sum(size * (size - 1) // 2 for size in group_sizes.values())
    for left_text, right_text in itertools.combinations(sorted(group_sizes), 2):
        left = group_shingles[left_text]
        right = group_shingles[right_text]
        if not left or not right:
            continue
        if (
            min(len(left), len(right)) / max(len(left), len(right))
            < MIN_JACCARD_LENGTH_RATIO
        ):
            continue
        if _jaccard(left, right) >= RATIONALE_DUP_JACCARD:
            dup_count += group_sizes[left_text] * group_sizes[right_text]
    total_pairs = rows * (rows - 1) // 2
    return dup_count / total_pairs, dup_count


def _normalization_k(meta: QuestionMeta | None, n: int) -> float | None:
    if meta is not None and meta.category_count is not None and meta.category_count > 1:
        return float(meta.category_count)
    if meta is not None and meta.question_type == "likert":
        return DEFAULT_LIKERT_K
    if n > 1:
        return float(n)
    return None


def _flag_and_status(
    *,
    n: int,
    top_share: float,
    effective_answers: float,
    rationale_dup_rate: float | None,
    rationale_dup_pair_count: int = 0,
) -> tuple[str | None, str]:
    if n < MIN_EVAL_N:
        return None, "skipped"
    rationale_low = (
        rationale_dup_rate is not None
        and rationale_dup_rate >= LOW_RATIONALE_DUP_RATE
        and rationale_dup_pair_count >= MIN_RATIONALE_DUP_PAIRS_FOR_LOW
    )
    low = (
        top_share >= LOW_TOP_SHARE and effective_answers <= LOW_EFFECTIVE_ANSWERS
    ) or rationale_low
    if low:
        return "low", "evaluated"
    if n <= MODERATE_SUPPRESS_MAX_N:
        return "ok", "evaluated"
    if (
        top_share >= MODERATE_TOP_SHARE
        or effective_answers <= MODERATE_EFFECTIVE_ANSWERS
    ):
        return "moderate", "evaluated"
    return "ok", "evaluated"


def compute_diversity(
    questions: Mapping[str, Sequence[tuple[Any, str]]],
    *,
    question_meta: Mapping[str, QuestionMeta] | None = None,
) -> DiversitySummary:
    """Compute diversity diagnostics per survey question.

    ``questions`` maps question id -> list of ``(answer value, rationale text)``
    pairs, one per trial. ``question_meta`` optionally supplies known category
    counts (K) for entropy normalization.
    """
    entries: list[QuestionDiversity] = []
    for qid in sorted(questions, key=_question_sort_key):
        responses = [
            (value, rationale if isinstance(rationale, str) else str(rationale))
            for value, rationale in questions[qid]
            if value is not None or (isinstance(rationale, str) and rationale.strip())
        ]
        values = [value for value, _ in responses if value is not None]
        n = len(values)
        meta = question_meta.get(qid) if question_meta else None
        counts: Counter[str] = Counter(canonical_answer(value) for value in values)
        if n:
            top_share = max(counts.values()) / n
            probs = [count / n for count in counts.values()]
            entropy = -sum(prob * math.log(prob) for prob in probs)
            pair_match_rate = (
                sum(count * (count - 1) for count in counts.values()) / (n * (n - 1))
                if n >= 2
                else 0.0
            )
        else:
            top_share = 0.0
            entropy = 0.0
            pair_match_rate = 0.0
        k = _normalization_k(meta, n)
        norm_entropy = (
            entropy / math.log(k) if k is not None and k > 1 and entropy > 0 else 0.0
        )
        effective_answers = math.exp(entropy)
        # Duplicate-rationale population matches n: rows without an answer
        # value do not take part in dup pairs even when they carry text.
        rationale_stats = _rationale_dup_stats(
            [rationale for value, rationale in responses if value is not None]
        )
        rationale_dup_rate = None if rationale_stats is None else rationale_stats[0]
        rationale_dup_pair_count = 0 if rationale_stats is None else rationale_stats[1]
        flag, status = _flag_and_status(
            n=n,
            top_share=top_share,
            effective_answers=effective_answers,
            rationale_dup_rate=rationale_dup_rate,
            rationale_dup_pair_count=rationale_dup_pair_count,
        )
        entries.append(
            QuestionDiversity(
                question_id=qid,
                n=n,
                top_share=top_share,
                norm_entropy=norm_entropy,
                effective_answers=effective_answers,
                pair_match_rate=pair_match_rate,
                rationale_dup_rate=rationale_dup_rate,
                flag=flag,
                status=status,
                category_count=k,
            )
        )
    return DiversitySummary(questions=entries)
