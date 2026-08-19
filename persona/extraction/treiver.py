"""The Treiver — runs two independent algorithms and merges their attributes.

Design (方案 B — parallel, then merge)
--------------------------------------
::

    prompt ─┬─▶ [A] RegexMatcher ───────────────▶ regex attributes ─┐
            │                                                        ├─▶ merge ─▶ attributes
            └─▶ retrieval (regex ∪ embed) ─▶ [B] LLMJudge ─▶ llm attributes ─┘

The two algorithms do **not** depend on each other's *output*:

* **[A] regex** scans the prompt literally and emits its own attributes.
* **[B] LLM judge** is fed a candidate set built by the *retrievers* — the union
  of the regex retriever's candidates and the embedding retriever's semantic
  candidates (:class:`~persona.treiver.embed_retriever.EmbedRetriever`) — so the
  judge can rule on dimensions the regex *matcher* would never surface (no
  literal overlap). The judge never sees regex's chosen values.

Both emit :class:`Attribute` records (same field shape as the extraction note).
After both run, :meth:`Treiver.match` **merges** them: by default the judge wins
a dimension both produced (it disambiguates), and the losing record is preserved
under ``Attribute.also``. A judge ``value: null`` ruling declines that dimension
and **vetoes** any matching regex attribute so unsupported claims do not survive.
The RAG "R" is the union retriever; the "G" is the judge.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from .embed_retriever import EmbedRetriever
from .llm_judge import LLMJudge
from .regex_matcher import RegexMatcher
from .schema import DimensionSchema, default_schema, load_schema

# Confidence assigned to a literal regex match. High but < 1.0: a whole-word
# hit is strong evidence but not proof of the intended sense.
_REGEX_CONFIDENCE = 0.7


@dataclass
class Attribute:
    """One recovered persona attribute (a ``(dimension_id, value)`` assignment).

    Mirrors the extracted-field shape in the extraction-quality rubric.
    """

    dimension_id: str
    value: str
    evidence: str | None
    method: str  # "regex" | "llm"
    confidence: float
    reason: str = ""
    # When both algorithms produced this dimension, the losing record is kept
    # here so a merge never silently discards the other algorithm's answer.
    also: "Attribute | None" = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class MatchResult:
    """Everything the treiver produced for one prompt.

    ``attributes`` is the merged view. ``regex_attributes`` / ``llm_attributes``
    are each algorithm's independent output (方案 B), so you can compare them or
    use one alone.
    """

    prompt: str
    attributes: list[Attribute]
    regex_attributes: list[Attribute] = field(default_factory=list)
    llm_attributes: list[Attribute] = field(default_factory=list)
    candidate_dimension_ids: list[str] = field(default_factory=list)
    used_llm: bool = False

    def as_dict(self) -> dict:
        return {
            "prompt": self.prompt,
            "attributes": [a.as_dict() for a in self.attributes],
            "regex_attributes": [a.as_dict() for a in self.regex_attributes],
            "llm_attributes": [a.as_dict() for a in self.llm_attributes],
            "persona": self.as_persona(),
            "candidate_dimension_ids": self.candidate_dimension_ids,
            "used_llm": self.used_llm,
        }

    def as_persona(self, source: str = "merged") -> dict[str, str]:
        """Collapse attributes into a ``{dimension_id: value}`` persona dict.

        ``source`` selects which algorithm's attributes to use:
        ``"merged"`` (default), ``"regex"``, or ``"llm"``.
        """
        attrs = {
            "merged": self.attributes,
            "regex": self.regex_attributes,
            "llm": self.llm_attributes,
        }.get(source, self.attributes)
        return {a.dimension_id: a.value for a in attrs}

    def value_of(self, dimension_id: str) -> str | None:
        """Convenience: the assigned value for a dimension, or None."""
        for attr in self.attributes:
            if attr.dimension_id == dimension_id:
                return attr.value
        return None


class Treiver:
    """Match free-text prompts to persona attributes.

    Parameters
    ----------
    schema:
        A :class:`DimensionSchema`. Defaults to the bundled taxonomy.
    schema_path:
        Alternative to ``schema`` — load the taxonomy from this JSON path.
    judge:
        A pre-built :class:`LLMJudge`. If omitted, one is created on demand the
        first time ``use_llm=True`` is requested (so no API key is needed unless
        you actually invoke the judge).
    embed:
        A pre-built :class:`EmbedRetriever`. If omitted, one is created on demand
        the first time the judge runs (so the embedding model loads only when the
        semantic retriever is actually used).
    """

    def __init__(
        self,
        schema: DimensionSchema | None = None,
        schema_path: str | Path | None = None,
        judge: LLMJudge | None = None,
        embed: EmbedRetriever | None = None,
    ) -> None:
        if schema is not None:
            self.schema = schema
        elif schema_path is not None:
            self.schema = load_schema(schema_path)
        else:
            self.schema = default_schema()

        self.regex = RegexMatcher(self.schema)
        self._judge = judge
        self._embed = embed

    def _get_embed(self) -> EmbedRetriever:
        if self._embed is None:
            self._embed = EmbedRetriever(self.schema)
        return self._embed

    def _get_judge(self) -> LLMJudge:
        if self._judge is None:
            self._judge = LLMJudge(self.schema)
        return self._judge

    def match(
        self,
        prompt: str,
        use_llm: bool = False,
        include_topic_only: bool = True,
        use_embed: bool = True,
        prefer: str = "llm",
    ) -> MatchResult:
        """Recover persona attributes from ``prompt`` (方案 B: parallel + merge).

        The two algorithms run **independently**:

        * regex always runs and produces ``result.regex_attributes``.
        * with ``use_llm=True`` the judge also runs, over a candidate set that is
          the *union* of the regex retriever's candidates and (when
          ``use_embed=True``) the embedding retriever's semantic candidates — so
          the judge can rule on dimensions regex never surfaced. Its output is
          ``result.llm_attributes``.

        ``result.attributes`` is the two merged (see ``prefer``); when the judge
        is off it's just the regex attributes. Judge ``null`` declines remove that
        dimension from the merged view (including regex hits).

        Parameters
        ----------
        prefer:
            On a dimension both algorithms produced a non-null value, which method
            wins the merged view — ``"llm"`` (default) or ``"regex"``. The loser
            is kept on the winner's ``Attribute.also``. A judge null still vetoes.
        """
        regex_attrs = self._run_regex(prompt)

        if not use_llm:
            regex_list = list(regex_attrs.values())
            return MatchResult(
                prompt=prompt,
                attributes=regex_list,
                regex_attributes=regex_list,
                llm_attributes=[],
                candidate_dimension_ids=list(regex_attrs.keys()),
                used_llm=False,
            )

        candidate_ids = self._retrieve_candidates(
            prompt, include_topic_only=include_topic_only, use_embed=use_embed
        )
        llm_attrs, declined_ids = self._run_llm(prompt, candidate_ids)

        merged = _merge(
            regex_attrs,
            llm_attrs,
            prefer=prefer,
            declined_ids=declined_ids,
        )
        return MatchResult(
            prompt=prompt,
            attributes=_ordered_by_candidates(merged, candidate_ids),
            regex_attributes=list(regex_attrs.values()),
            llm_attributes=list(llm_attrs.values()),
            candidate_dimension_ids=candidate_ids,
            used_llm=True,
        )

    # -- the two independent algorithms --------------------------------------

    def _run_regex(self, prompt: str) -> dict[str, Attribute]:
        """Algorithm A: regex. First (leftmost) hit per dimension wins."""
        attrs: dict[str, Attribute] = {}
        for hit in self.regex.match(prompt):
            attrs.setdefault(
                hit.dimension_id,
                Attribute(
                    dimension_id=hit.dimension_id,
                    value=hit.value,
                    evidence=hit.evidence,
                    method="regex",
                    confidence=_REGEX_CONFIDENCE,
                ),
            )
        return attrs

    def _run_llm(
        self, prompt: str, candidate_ids: list[str]
    ) -> tuple[dict[str, Attribute], set[str]]:
        """Algorithm B: the judge, over the retrieved candidate set.

        Returns ``(positive_attrs, declined_ids)``. A ``value is None`` ruling
        means the text does not support that dimension — those ids are returned
        separately so :func:`_merge` can veto matching regex attributes.
        """
        attrs: dict[str, Attribute] = {}
        declined: set[str] = set()
        for r in self._get_judge().judge(prompt, candidate_ids):
            if r.value is None:
                # Judge declined — carry the veto to merge (no over-claim).
                declined.add(r.dimension_id)
                continue
            attrs[r.dimension_id] = Attribute(
                dimension_id=r.dimension_id,
                value=r.value,
                evidence=r.evidence,
                method="llm",
                confidence=r.confidence,
                reason=r.reason,
            )
        return attrs, declined

    def _retrieve_candidates(
        self, prompt: str, include_topic_only: bool, use_embed: bool
    ) -> list[str]:
        """The RAG "R": union of the regex and embedding retrievers' candidates."""
        ids = self.regex.candidate_dimension_ids(
            prompt, include_topic_only=include_topic_only
        )
        if use_embed:
            try:
                ids = ids + self._get_embed().candidate_dimension_ids(prompt)
            except Exception:
                pass  # embedding backend unavailable → regex candidates only
        return _ordered_unique(ids)


def _ordered_unique(items) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out


def _ordered_by_candidates(attrs, candidate_ids: list[str]) -> list[Attribute]:
    """Sort attributes to follow candidate (prompt-forward) order."""
    rank = {dim_id: i for i, dim_id in enumerate(candidate_ids)}
    return sorted(attrs, key=lambda a: rank.get(a.dimension_id, len(rank)))


def _merge(
    regex_attrs: dict[str, Attribute],
    llm_attrs: dict[str, Attribute],
    prefer: str = "llm",
    declined_ids: set[str] | None = None,
) -> list[Attribute]:
    """Merge the two algorithms' attributes into one per dimension.

    Union of dimensions, except ids in ``declined_ids`` (judge ``value: null``)
    are omitted so a decline can veto a regex over-claim. For a dimension both
    produced with values, ``prefer`` picks the winner; the loser is attached to
    ``winner.also`` so competing non-null answers are not silently dropped.

    Under ``prefer="regex"``, a judge decline still vetoes: null means "not
    supported by the text", not an alternate value preference.
    """
    declined = declined_ids or set()
    out: list[Attribute] = []
    all_ids = list(regex_attrs) + [d for d in llm_attrs if d not in regex_attrs]
    for dim_id in all_ids:
        if dim_id in declined:
            continue
        r = regex_attrs.get(dim_id)
        m = llm_attrs.get(dim_id)
        if r and m:
            winner, loser = (m, r) if prefer == "llm" else (r, m)
            out.append(replace(winner, also=loser))
        else:
            out.append(r or m)
    return out
