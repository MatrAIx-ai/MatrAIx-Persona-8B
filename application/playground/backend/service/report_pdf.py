"""Generate downloadable MatrAIx PDF reports for Harbor batch jobs and trials."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from fpdf import FPDF

from backend.service.llm_usage_view import (
    format_cost_usd,
    format_token_count,
    usage_from_job_result,
    usage_meta_lines,
)

# Portable Helvetica is Latin-1 only; normalize common Unicode punctuation.
_UNICODE_MAP = str.maketrans(
    {
        "\u2013": "-",  # en dash
        "\u2014": "-",  # em dash
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00b7": "-",
        "\u00d7": "x",
        "\u2212": "-",
        "\u00a0": " ",
        "\u2022": "-",
        "\u2192": "->",
        "\ufeff": "",
    }
)


def _safe(value: object, *, limit: int | None = None) -> str:
    text = " ".join(str(value if value is not None else "").translate(_UNICODE_MAP).split())
    if limit is not None and len(text) > limit:
        text = text[: max(0, limit - 1)].rstrip() + "..."
    return text.encode("latin-1", "replace").decode("latin-1")


def _fmt_num(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        if value == int(value):
            return str(int(value))
        return f"{value:.2f}"
    return _safe(value)


def _humanize(value: object) -> str:
    text = _safe(value)
    if not text or text == "-":
        return text
    if re.fullmatch(r"[a-z0-9]+(?:_[a-z0-9]+)+", text):
        return text.replace("_", " ").strip().capitalize()
    return text


def _pct(count: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round(100.0 * count / total)}%"


def _bar(count: int, total: int, *, width: int = 18) -> str:
    if total <= 0 or count <= 0:
        return "." * width
    filled = max(1, round(width * count / total))
    return "#" * min(width, filled) + "." * max(0, width - filled)


class _ReportPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=18)
        self.set_margins(18, 16, 18)
        self._in_header = False

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self._in_header = True
        self.set_font("Helvetica", "B", 8)
        self.set_text_color(0, 118, 194)
        self.cell(0, 4, "MatrAIx", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 118, 194)
        self.set_line_width(0.35)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(5)
        self._in_header = False

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, f"Page {self.page_no()}/{{nb}}", align="C")

    def content_width(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def ensure_space(self, height: float) -> None:
        if self._in_header:
            return
        if self.get_y() + height > self.h - self.b_margin:
            self.add_page()

    def cover(self, *, eyebrow: str, title: str, meta_lines: list[str]) -> None:
        self.add_page()
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(0, 118, 194)
        self.cell(0, 5, "MatrAIx", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(0, 118, 194)
        self.set_line_width(0.45)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(8)
        self.set_font("Helvetica", "", 11)
        self.set_text_color(0, 118, 194)
        self.cell(0, 6, _safe(eyebrow), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(17, 23, 31)
        self.multi_cell(0, 7, _safe(title, limit=160), new_x="LMARGIN", new_y="NEXT")
        self.ln(3)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(71, 85, 105)
        for line in meta_lines:
            if line:
                self.multi_cell(0, 5, _safe(line, limit=220), new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def section(self, title: str) -> None:
        self.ensure_space(16)
        self.ln(2)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(15, 23, 42)
        self.cell(0, 7, _safe(title), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(203, 213, 225)
        self.set_line_width(0.25)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)

    def h3(self, title: str) -> None:
        self.ensure_space(12)
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(30, 41, 59)
        self.multi_cell(0, 5.5, _safe(title, limit=240), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def muted(self, text: str) -> None:
        self.ensure_space(8)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(100, 116, 139)
        self.multi_cell(0, 4.5, _safe(text, limit=300), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body(self, text: str, *, size: int = 10) -> None:
        self.ensure_space(10)
        self.set_font("Helvetica", "", size)
        self.set_text_color(51, 65, 85)
        self.multi_cell(0, 5, _safe(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(0.5)

    def bullet(self, text: str) -> None:
        self.ensure_space(8)
        self.set_font("Helvetica", "", 9)
        self.set_text_color(51, 65, 85)
        self.multi_cell(0, 4.5, f"- {_safe(text, limit=4000)}", new_x="LMARGIN", new_y="NEXT")

    def kv_block(self, rows: list[tuple[str, str]]) -> None:
        """Single-column key/value rows — never splits across pages mid-row."""
        if not rows:
            self.body("No data.")
            return
        label_w = 42.0
        value_w = self.content_width() - label_w
        for label, value in rows:
            left = _safe(label, limit=40)
            right = _safe(value if value not in (None, "") else "-", limit=4000)
            approx_lines = max(1, (len(right) // 70) + 1)
            self.ensure_space(5.0 * approx_lines + 2)
            y0 = self.get_y()
            self.set_font("Helvetica", "B", 9)
            self.set_text_color(100, 116, 139)
            self.set_xy(self.l_margin, y0)
            self.multi_cell(label_w, 5, left, new_x="LMARGIN", new_y="NEXT")
            y_left = self.get_y()
            self.set_xy(self.l_margin + label_w, y0)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(30, 41, 59)
            self.multi_cell(value_w, 5, right, new_x="LMARGIN", new_y="NEXT")
            self.set_y(max(y_left, self.get_y()) + 0.8)

    def metric_strip(self, items: list[tuple[str, str]]) -> None:
        if not items:
            return
        self.ensure_space(16)
        col_w = self.content_width() / max(1, len(items))
        y0 = self.get_y()
        for idx, (label, value) in enumerate(items):
            x = self.l_margin + idx * col_w
            self.set_xy(x, y0)
            self.set_font("Helvetica", "", 8)
            self.set_text_color(100, 116, 139)
            self.cell(col_w - 2, 4, _safe(label, limit=24))
            self.set_xy(x, y0 + 4)
            self.set_font("Helvetica", "B", 12)
            self.set_text_color(15, 23, 42)
            self.cell(col_w - 2, 6, _safe(value, limit=18))
        self.set_y(y0 + 12)
        self.ln(2)

    def count_rows(
        self,
        rows: list[tuple[str, int]],
        *,
        total: int | None = None,
    ) -> None:
        if not rows:
            self.body("No responses.")
            return
        denom = total if total is not None else sum(max(0, c) for _, c in rows)
        for label, count in rows:
            self.ensure_space(10)
            self.set_font("Helvetica", "", 9)
            self.set_text_color(30, 41, 59)
            self.multi_cell(0, 4.2, _safe(label, limit=100), new_x="LMARGIN", new_y="NEXT")
            self.set_font("Courier", "", 8)
            self.set_text_color(71, 85, 105)
            self.multi_cell(
                0,
                4,
                _safe(f"  {count} ({_pct(count, denom)})  {_bar(count, denom)}", limit=60),
                new_x="LMARGIN",
                new_y="NEXT",
            )
            self.ln(0.5)
        self.ln(1)

    def card_start(self) -> None:
        self.ensure_space(20)
        self.set_draw_color(226, 232, 240)
        self.set_line_width(0.2)
        y = self.get_y()
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.ln(3)


def _choice_label(context: dict[str, Any], value: object) -> str:
    options = context.get("choiceOptions") if isinstance(context.get("choiceOptions"), list) else []
    raw = str(value if value is not None else "")
    for option in options:
        if isinstance(option, dict) and str(option.get("id")) == raw:
            label = option.get("label")
            if label:
                return _safe(label)
    return _humanize(raw)


def _primary_facet(context: dict[str, Any]) -> dict[str, Any] | None:
    facets = context.get("facets") if isinstance(context.get("facets"), list) else []
    for facet in facets:
        if isinstance(facet, dict) and facet.get("role") == "primary":
            return facet
    for facet in facets:
        if isinstance(facet, dict):
            return facet
    return None


def _is_survey_aggregation(contexts: list[Any], application_type: str | None) -> bool:
    if (application_type or "").lower() == "survey":
        return True
    return any(
        isinstance(ctx, dict) and ctx.get("contextType") == "question_response"
        for ctx in contexts
    )


def _plain_text_from_markdown(md: object, *, limit: int | None = 4000) -> str:
    text = str(md or "")
    if not text.strip():
        return ""
    text = text.replace("\r\n", "\n")
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s+", "- ", text, flags=re.M)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return _safe(text, limit=limit)


def task_path_from_job(job: dict[str, Any] | None) -> str | None:
    job = job or {}
    for key in ("taskPath", "task_path"):
        raw = str(job.get(key) or "").strip()
        if raw:
            return raw
    config = job.get("config") if isinstance(job.get("config"), dict) else {}
    tasks = config.get("tasks") if isinstance(config.get("tasks"), list) else []
    if tasks and isinstance(tasks[0], dict):
        path = str(tasks[0].get("path") or "").strip()
        if path:
            return path
    return None


def _persona_pool_from_job(job: dict[str, Any] | None) -> str | None:
    job = job or {}
    config = job.get("config") if isinstance(job.get("config"), dict) else {}
    meta = config.get("_job_meta") if isinstance(config.get("_job_meta"), dict) else {}
    for source in (job, config, meta):
        if not isinstance(source, dict):
            continue
        for key in ("personaPool", "persona_pool"):
            raw = str(source.get(key) or "").strip()
            if raw:
                return raw
    return None


def _render_batch_front_matter(
    pdf: _ReportPDF,
    *,
    job: dict[str, Any] | None,
    task_detail: dict[str, Any] | None,
) -> None:
    """UI-parity preface: task brief + persona strategy + cohort (before results)."""
    job = job or {}
    detail = task_detail if isinstance(task_detail, dict) else {}
    strategy = detail.get("personaStrategy")
    if not isinstance(strategy, dict):
        strategy = job.get("personaStrategy") if isinstance(job.get("personaStrategy"), dict) else {}

    title = (
        str(detail.get("title") or "").strip()
        or str(job.get("taskTitle") or "").strip()
        or str(job.get("taskName") or "").strip()
    )
    description = (
        str(detail.get("description") or "").strip()
        or str(job.get("description") or "").strip()
    )
    instruction = _plain_text_from_markdown(detail.get("instructionMarkdown"))
    context = _plain_text_from_markdown(detail.get("contextMarkdown"))
    domain = str(detail.get("domain") or job.get("domain") or "").strip()
    difficulty = str(detail.get("difficulty") or job.get("difficulty") or "").strip()
    tags = detail.get("tags") if isinstance(detail.get("tags"), list) else job.get("tags")
    tag_line = ", ".join(str(t) for t in (tags or []) if str(t).strip()) if tags else ""

    if any([title, description, instruction, context, domain, difficulty, tag_line]):
        pdf.section("Task")
        if title:
            pdf.h3(title)
        meta_bits = [p for p in (domain, difficulty, tag_line) if p]
        if meta_bits:
            pdf.muted(" · ".join(meta_bits))
        if description:
            pdf.body(description, size=9)
        if context:
            pdf.muted("Context")
            pdf.body(context, size=9)
        if instruction and instruction != description:
            pdf.muted("Instruction")
            # Cap front-matter length so huge task docs do not dominate the PDF.
            body = instruction
            if len(body) > 8000:
                body = body[:8000] + "\n… (instruction truncated)"
            pdf.body(body, size=9)

    if strategy:
        pdf.section("Persona strategy")
        rows: list[tuple[str, str]] = []
        sampling = strategy.get("sampling") if isinstance(strategy.get("sampling"), dict) else {}
        mode = sampling.get("mode")
        if mode:
            rows.append(("Mode", _safe(mode)))
        allocation = sampling.get("allocation")
        if allocation:
            rows.append(("Allocation", _safe(allocation)))
        if allocation == "perCell" and sampling.get("perCell") is not None:
            rows.append(("Per cell", _fmt_num(sampling.get("perCell"))))
        elif sampling.get("sampleSize") is not None:
            rows.append(("Sample size", _fmt_num(sampling.get("sampleSize"))))
        if strategy.get("seed") is not None:
            rows.append(("Seed", _fmt_num(strategy.get("seed"))))
        stratify = sampling.get("fields")
        if isinstance(stratify, list) and stratify:
            rows.append(("Stratify", ", ".join(_safe(x) for x in stratify)))
        sources = strategy.get("sources")
        if isinstance(sources, list) and sources:
            rows.append(("Sources", ", ".join(_safe(x) for x in sources)))
        filters = strategy.get("dimensionFilters")
        if isinstance(filters, dict) and filters:
            bits = []
            for key, value in filters.items():
                if isinstance(value, list):
                    bits.append(f"{_humanize(key)}={','.join(_safe(v) for v in value)}")
                else:
                    bits.append(f"{_humanize(key)}={_safe(value)}")
            rows.append(("Filters", "; ".join(bits)))
        if rows:
            pdf.kv_block(rows)

    pool = _persona_pool_from_job(job)
    trials = job.get("trials") if isinstance(job.get("trials"), list) else []
    roster: list[str] = []
    for trial in trials:
        if not isinstance(trial, dict):
            continue
        name = str(trial.get("personaName") or trial.get("personaId") or "").strip()
        if name and name not in roster:
            roster.append(name)
    if pool or roster:
        pdf.section("Cohort")
        rows = []
        if pool:
            rows.append(("Persona pool", _safe(pool, limit=160)))
        if roster:
            rows.append((f"Personas ({len(roster)})", f"{len(roster)} unique"))
        if rows:
            pdf.kv_block(rows)
        if roster:
            pdf.muted("Full persona roster")
            for name in roster:
                pdf.bullet(_safe(name, limit=120))


def _coverage_metrics(coverage: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        ("Trials", _fmt_num(coverage.get("trialCount"))),
        ("Completed", _fmt_num(coverage.get("completedTrials"))),
        ("Pending", _fmt_num(coverage.get("pendingTrials"))),
        ("Artifacts", _fmt_num(coverage.get("artifactReadyTrials"))),
    ]


def _job_meta_lines(job: dict[str, Any] | None, aggregation: dict[str, Any]) -> list[str]:
    job = job or {}
    launch = job.get("launch") if isinstance(job.get("launch"), dict) else {}
    result = job.get("result") if isinstance(job.get("result"), dict) else {}
    config = job.get("config") if isinstance(job.get("config"), dict) else {}
    reporting = aggregation.get("reporting") if isinstance(aggregation.get("reporting"), dict) else {}
    generated = aggregation.get("generatedAt") or datetime.now(timezone.utc).isoformat()

    status = launch.get("status")
    if not status:
        if result.get("finished_at"):
            status = "completed"
        elif result.get("started_at"):
            status = "running"
        else:
            status = "unknown"

    lines = [
        f"Generated: {_safe(generated)}",
        f"Status: {_safe(status)}"
        + (f" · exit {_safe(launch.get('exitCode'))}" if launch.get("exitCode") is not None else ""),
    ]
    if result.get("started_at") or result.get("finished_at"):
        lines.append(
            f"Run window: {_safe(result.get('started_at') or '-')} -> {_safe(result.get('finished_at') or '-')}"
        )
    if launch.get("configPath"):
        lines.append(f"Config: {_safe(launch.get('configPath'))}")
    agents = config.get("agents") if isinstance(config.get("agents"), list) else []
    if agents and isinstance(agents[0], dict) and agents[0].get("model_name"):
        lines.append(f"Agent model: {_safe(agents[0].get('model_name'))}")
    lines.extend(usage_meta_lines(usage_from_job_result(result)))
    if reporting:
        status_r = _safe(reporting.get("status") or "-")
        if status_r not in ("-", "not_applicable"):
            model = f" · {_safe(reporting.get('model'))}" if reporting.get("model") else ""
            lines.append(f"LLM report: {status_r}{model}")
    return lines


def _usage_metric_pairs(usage: dict[str, Any] | None) -> list[tuple[str, str]]:
    if not usage:
        return []
    pairs: list[tuple[str, str]] = []
    cost = usage.get("costUsd")
    if isinstance(cost, (int, float)):
        pairs.append(("Cost", format_cost_usd(float(cost))))
    n_in = usage.get("nInputTokens")
    if isinstance(n_in, int):
        pairs.append(("Input tokens", format_token_count(n_in)))
    n_out = usage.get("nOutputTokens")
    if isinstance(n_out, int):
        pairs.append(("Output tokens", format_token_count(n_out)))
    n_cache = usage.get("nCacheTokens")
    if isinstance(n_cache, int) and n_cache > 0:
        pairs.append(("Cache tokens", format_token_count(n_cache)))
    return pairs


def _render_facet_distribution(
    pdf: _ReportPDF,
    facet: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> None:
    kind = str(facet.get("kind") or "")
    present = int(facet.get("presentCount") or 0)
    context = context or {}

    if kind == "categorical":
        categorical = facet.get("categorical") if isinstance(facet.get("categorical"), dict) else {}
        counts = categorical.get("counts") if isinstance(categorical.get("counts"), list) else []
        options = context.get("choiceOptions") if isinstance(context.get("choiceOptions"), list) else []
        by_id = {
            str(item.get("value")): int(item.get("count") or 0)
            for item in counts
            if isinstance(item, dict)
        }
        rows: list[tuple[str, int]] = []
        seen: set[str] = set()
        if options:
            for option in options:
                if not isinstance(option, dict):
                    continue
                oid = str(option.get("id") or "")
                seen.add(oid)
                rows.append((_choice_label(context, oid), by_id.get(oid, 0)))
            for value, count in by_id.items():
                if value not in seen:
                    rows.append((_humanize(value), count))
        else:
            rows = [
                (_choice_label(context, item.get("value")), int(item.get("count") or 0))
                for item in counts
                if isinstance(item, dict)
            ]
        pdf.muted(f"{present} responses · {len(rows)} categories")
        pdf.count_rows(rows, total=present or None)
        return

    if kind == "numerical":
        numerical = facet.get("numerical") if isinstance(facet.get("numerical"), dict) else {}
        scale_bits = []
        if context.get("scaleMin") is not None or facet.get("scaleMin") is not None:
            lo = context.get("scaleMin", facet.get("scaleMin"))
            hi = context.get("scaleMax", facet.get("scaleMax"))
            scale_bits.append(f"scale {_fmt_num(lo)}-{_fmt_num(hi)}")
        pdf.muted(
            "avg {avg} · min {min} · max {max} · n={n}{scale}".format(
                avg=_fmt_num(numerical.get("avg")),
                min=_fmt_num(numerical.get("min")),
                max=_fmt_num(numerical.get("max")),
                n=_fmt_num(numerical.get("count") or present),
                scale=(f" · {scale_bits[0]}" if scale_bits else ""),
            )
        )
        counts = numerical.get("counts") if isinstance(numerical.get("counts"), list) else []
        if counts:
            rows = [
                (_safe(item.get("value")), int(item.get("count") or 0))
                for item in counts
                if isinstance(item, dict)
            ]

            def _sort_key(row: tuple[str, int]) -> tuple[int, float | str]:
                try:
                    return (0, float(row[0]))
                except ValueError:
                    return (1, row[0])

            rows.sort(key=_sort_key)
            pdf.count_rows(rows, total=present or None)
        return

    if kind == "textual":
        textual = facet.get("textual") if isinstance(facet.get("textual"), dict) else {}
        if textual.get("summary"):
            pdf.body(str(textual.get("summary")), size=9)
        samples = textual.get("samples") if isinstance(textual.get("samples"), list) else []
        if samples:
            pdf.muted("Sample answers")
            shown = samples[:40]
            for sample in shown:
                pdf.bullet(_safe(sample, limit=600))
            if len(samples) > len(shown):
                pdf.muted(f"… ({len(samples) - len(shown)} more samples truncated)")
        return

    pdf.kv_block(
        [
            ("Kind", kind or "-"),
            ("Present / missing", f"{facet.get('presentCount', 0)} / {facet.get('missingCount', 0)}"),
        ]
    )


def _render_summaries(pdf: _ReportPDF, summaries: list[Any], *, heading: str = "Summaries") -> None:
    items = [s for s in summaries if isinstance(s, dict)]
    if not items:
        return
    pdf.muted(heading)
    for summary in items:
        title = summary.get("title") or summary.get("id") or "Summary"
        auto = " · auto" if summary.get("auto") else ""
        lens = f" · {_safe(summary.get('lens'))}" if summary.get("lens") else ""
        status = f" · {_safe(summary.get('status'))}" if summary.get("status") else ""
        pdf.muted(f"{_safe(title)}{auto}{lens}{status}")
        if summary.get("error"):
            pdf.body(f"Error: {_safe(summary.get('error'), limit=400)}", size=8)
        overall = summary.get("overall") if isinstance(summary.get("overall"), dict) else {}
        if overall.get("summary"):
            pdf.body(str(overall.get("summary")), size=9)
        buckets = summary.get("buckets") if isinstance(summary.get("buckets"), list) else []
        shown = buckets[:24]
        for bucket in shown:
            if not isinstance(bucket, dict):
                continue
            text = _safe(bucket.get("summary") or "", limit=500)
            line = f"{_safe(bucket.get('bucket'))} (n={_fmt_num(bucket.get('count'))})"
            if text:
                line += f": {text}"
            pdf.bullet(line)
            samples = bucket.get("samples") if isinstance(bucket.get("samples"), list) else []
            for sample in samples[:4]:
                pdf.bullet(f"  · {_safe(sample, limit=280)}")
        if len(buckets) > len(shown):
            pdf.muted(f"… ({len(buckets) - len(shown)} more summary buckets truncated)")


def _render_judges(pdf: _ReportPDF, judges: list[Any]) -> None:
    items = [j for j in judges if isinstance(j, dict)]
    if not items:
        return
    pdf.muted("Judges / signal scans")
    for judge in items:
        title = judge.get("title") or judge.get("id") or "Judge"
        status = f" · {_safe(judge.get('status'))}" if judge.get("status") else ""
        pdf.muted(f"{_safe(title)}{status}")
        if judge.get("overallAssessment"):
            pdf.body(str(judge.get("overallAssessment")), size=9)
        if judge.get("error"):
            pdf.body(f"Error: {_safe(judge.get('error'), limit=400)}", size=8)
        signal_stats = judge.get("signalStats") if isinstance(judge.get("signalStats"), list) else []
        if signal_stats:
            pdf.muted("Signal prevalence")
            for stat in signal_stats[:24]:
                if not isinstance(stat, dict):
                    continue
                present = int(stat.get("present") or 0)
                total = int(stat.get("total") or 0)
                pct = f" ({present * 100 // total}%)" if total else ""
                pdf.bullet(
                    f"{_safe(stat.get('label') or stat.get('key'))}: "
                    f"{present}/{total}{pct}"
                )
                examples = stat.get("examples") if isinstance(stat.get("examples"), list) else []
                for example in examples[:3]:
                    pdf.bullet(f"  · {_safe(example, limit=240)}")
        buckets = judge.get("buckets") if isinstance(judge.get("buckets"), list) else []
        shown = buckets[:16]
        for bucket in shown:
            if not isinstance(bucket, dict):
                continue
            pdf.bullet(
                f"{_safe(bucket.get('bucket'))} (n={_fmt_num(bucket.get('count'))})"
                + (f": {_safe(bucket.get('assessment'), limit=320)}" if bucket.get("assessment") else "")
            )
            samples = bucket.get("samples") if isinstance(bucket.get("samples"), list) else []
            for sample in samples[:3]:
                pdf.bullet(f"  · {_safe(sample, limit=240)}")
        if len(buckets) > len(shown):
            pdf.muted(f"… ({len(buckets) - len(shown)} more judge buckets truncated)")


def _cross_facet_views(context: dict[str, Any]) -> list[dict[str, Any]]:
    views = context.get("crossFacetViews")
    if not isinstance(views, list) or not views:
        views = context.get("relationships")
    if not isinstance(views, list):
        return []
    return [v for v in views if isinstance(v, dict)]


def _render_cross_facet_views(pdf: _ReportPDF, context: dict[str, Any]) -> None:
    views = _cross_facet_views(context)
    if not views:
        return
    pdf.muted("Cross-facet views")
    for view in views:
        vtype = _safe(view.get("type") or "cross").replace("_", " ")
        primary = _safe(view.get("primaryFacetKey") or "")
        text_key = _safe(view.get("textFacetKey") or "")
        bits = [vtype]
        if primary:
            bits.append(f"by {primary}")
        if text_key:
            bits.append(f"text={text_key}")
        pdf.muted(" · ".join(bits))
        buckets = view.get("buckets") if isinstance(view.get("buckets"), list) else []
        shown = buckets[:20]
        for bucket in shown:
            if not isinstance(bucket, dict):
                continue
            pdf.bullet(
                f"{_safe(bucket.get('category'))} (n={_fmt_num(bucket.get('count'))})"
            )
            samples = bucket.get("samples") if isinstance(bucket.get("samples"), list) else []
            for sample in samples[:6]:
                pdf.bullet(f"  · {_safe(sample, limit=320)}")
        if len(buckets) > len(shown):
            pdf.muted(f"… ({len(buckets) - len(shown)} more cross-facet buckets truncated)")


def _render_context_analysis(pdf: _ReportPDF, context: dict[str, Any]) -> None:
    """Summaries, judges, and cross-facets — Detailed report parity."""
    summaries = context.get("summaries") if isinstance(context.get("summaries"), list) else []
    auto = [s for s in summaries if isinstance(s, dict) and s.get("auto")]
    custom = [s for s in summaries if isinstance(s, dict) and not s.get("auto")]
    if auto:
        _render_summaries(pdf, auto, heading="Auto summaries")
    if custom:
        _render_summaries(pdf, custom, heading="Custom summaries")
    judges = context.get("judges") if isinstance(context.get("judges"), list) else []
    _render_judges(pdf, judges)
    _render_cross_facet_views(pdf, context)


def _render_question_context(pdf: _ReportPDF, context: dict[str, Any], *, index: int) -> None:
    pdf.card_start()
    label = context.get("label") or context.get("key") or f"Question {index}"
    qtype = _safe(context.get("questionType") or "question")
    pdf.h3(f"Q{index}. {_safe(label, limit=220)}")
    pdf.muted(qtype.replace("_", " "))
    facets = context.get("facets") if isinstance(context.get("facets"), list) else []
    facet_list = [f for f in facets if isinstance(f, dict)]
    if not facet_list:
        pdf.body("No response data for this question.")
    else:
        for facet in facet_list:
            facet_label = facet.get("label") or facet.get("key") or "Signal"
            role = facet.get("role")
            role_bit = f" · {_safe(role)}" if role else ""
            if len(facet_list) > 1 or role not in (None, "primary"):
                pdf.muted(f"{_safe(facet_label)}{role_bit}")
            _render_facet_distribution(pdf, facet, context=context)
    _render_context_analysis(pdf, context)


def _render_generic_context(pdf: _ReportPDF, context: dict[str, Any]) -> None:
    pdf.card_start()
    label = context.get("label") or context.get("key") or "Context"
    bits = []
    if context.get("contextType"):
        bits.append(_safe(context.get("contextType")).replace("_", " "))
    if context.get("questionType"):
        bits.append(_safe(context.get("questionType")).replace("_", " "))
    pdf.h3(_safe(label, limit=220))
    if bits:
        pdf.muted(" · ".join(bits))
    facets = context.get("facets") if isinstance(context.get("facets"), list) else []
    facet_list = [f for f in facets if isinstance(f, dict)]
    for facet in facet_list:
        facet_label = facet.get("label") or facet.get("key") or "Signal"
        if len(facet_list) > 1:
            pdf.muted(_safe(facet_label))
        _render_facet_distribution(pdf, facet, context=context)
    _render_context_analysis(pdf, context)


def _render_persona_insights(pdf: _ReportPDF, contexts: list[Any]) -> None:
    """Persona distributions + standalone facets from all contexts (Detailed tab)."""
    cards: list[tuple[str, dict[str, Any]]] = []
    standalones: list[tuple[str, dict[str, Any]]] = []
    for context in contexts:
        if not isinstance(context, dict):
            continue
        ctx_label = _safe(context.get("label") or context.get("key") or "Context", limit=80)
        dists = context.get("personaDistributions")
        if isinstance(dists, list):
            for dist in dists:
                if isinstance(dist, dict):
                    cards.append((ctx_label, dist))
        alone = context.get("personaStandaloneFacets")
        if isinstance(alone, list):
            for facet in alone:
                if isinstance(facet, dict):
                    standalones.append((ctx_label, facet))
    if not cards and not standalones:
        return

    pdf.section("Persona insights")
    for ctx_label, dist in cards:
        pdf.card_start()
        title = dist.get("facetLabel") or dist.get("facetKey") or "Distribution"
        group = dist.get("groupByLabel") or dist.get("groupByPersonaDimension") or "persona"
        pdf.h3(_safe(title, limit=160))
        pdf.muted(f"{ctx_label} · by {_safe(group)} · n={_fmt_num(dist.get('total'))}")
        buckets = dist.get("buckets") if isinstance(dist.get("buckets"), list) else []
        kind = str(dist.get("kind") or "")
        for bucket in buckets[:30]:
            if not isinstance(bucket, dict):
                continue
            name = _safe(bucket.get("bucket"))
            count = int(bucket.get("count") or 0)
            if kind == "numerical":
                numerical = bucket.get("numerical") if isinstance(bucket.get("numerical"), dict) else {}
                pdf.bullet(
                    f"{name} (n={count}): avg {_fmt_num(numerical.get('avg'))} · "
                    f"min {_fmt_num(numerical.get('min'))} · max {_fmt_num(numerical.get('max'))}"
                )
            elif kind == "categorical":
                categorical = bucket.get("categorical") if isinstance(bucket.get("categorical"), dict) else {}
                counts = categorical.get("counts") if isinstance(categorical.get("counts"), list) else []
                bits = []
                for item in counts[:8]:
                    if isinstance(item, dict):
                        bits.append(f"{_safe(item.get('value'))}={_fmt_num(item.get('count'))}")
                pdf.bullet(f"{name} (n={count}): " + (", ".join(bits) if bits else "-"))
            else:
                pdf.bullet(f"{name} (n={count})")
        if len(buckets) > 30:
            pdf.muted(f"… ({len(buckets) - 30} more persona buckets truncated)")

    for ctx_label, facet in standalones:
        pdf.card_start()
        pdf.h3(_safe(facet.get("label") or facet.get("key") or "Standalone", limit=160))
        pdf.muted(ctx_label)
        _render_facet_distribution(pdf, facet)


def build_batch_report_pdf(
    *,
    job_name: str,
    job: dict[str, Any] | None,
    aggregation: dict[str, Any],
    task_detail: dict[str, Any] | None = None,
) -> bytes:
    job = job or {}
    coverage = aggregation.get("coverage") if isinstance(aggregation.get("coverage"), dict) else {}
    fields = aggregation.get("fields") if isinstance(aggregation.get("fields"), list) else []
    contexts = aggregation.get("contexts") if isinstance(aggregation.get("contexts"), list) else []
    trials = job.get("trials") if isinstance(job.get("trials"), list) else []
    application_type = job.get("applicationType")
    if not application_type:
        config = job.get("config") if isinstance(job.get("config"), dict) else {}
        agents = config.get("agents") if isinstance(config.get("agents"), list) else []
        if agents and isinstance(agents[0], dict):
            agent_name = str(agents[0].get("name") or "")
            if "survey" in agent_name:
                application_type = "survey"

    is_survey = _is_survey_aggregation(contexts, str(application_type) if application_type else None)
    questions = [
        ctx
        for ctx in contexts
        if isinstance(ctx, dict) and ctx.get("contextType") == "question_response"
    ]
    other_contexts = [
        ctx
        for ctx in contexts
        if isinstance(ctx, dict) and ctx.get("contextType") != "question_response"
    ]
    trial_summary = next(
        (
            ctx
            for ctx in other_contexts
            if isinstance(ctx, dict) and ctx.get("contextType") == "trial_summary"
        ),
        None,
    )
    detail_contexts = [
        ctx
        for ctx in other_contexts
        if not (isinstance(ctx, dict) and ctx.get("contextType") == "trial_summary")
    ]

    detail = task_detail if isinstance(task_detail, dict) else {}
    cover_title = (
        str(detail.get("title") or "").strip()
        or str(job.get("taskTitle") or "").strip()
        or job_name
    )

    pdf = _ReportPDF()
    pdf.alias_nb_pages()
    pdf.cover(
        eyebrow="Persona-task batch report" + (" · Survey" if is_survey else ""),
        title=cover_title,
        meta_lines=[f"Job: {_safe(job_name, limit=120)}"] + _job_meta_lines(job, aggregation),
    )

    _render_batch_front_matter(pdf, job=job, task_detail=detail or None)

    pdf.section("Overview")
    pdf.metric_strip(_coverage_metrics(coverage))
    usage_pairs = _usage_metric_pairs(usage_from_job_result(job.get("result")))
    if usage_pairs:
        pdf.metric_strip(usage_pairs)
    if is_survey and questions:
        type_counts: dict[str, int] = {}
        for ctx in questions:
            qtype = str(ctx.get("questionType") or "unknown").replace("_", " ")
            type_counts[qtype] = type_counts.get(qtype, 0) + 1
        mix = ", ".join(f"{count} {label}" for label, count in sorted(type_counts.items()))
        pdf.body(f"{len(questions)} questions · {mix}", size=9)
        # Survey coverage extras when present on question facets.
        answered = []
        for ctx in questions:
            facets = ctx.get("facets") if isinstance(ctx.get("facets"), list) else []
            primary = next(
                (f for f in facets if isinstance(f, dict) and f.get("role") == "primary"),
                facets[0] if facets and isinstance(facets[0], dict) else None,
            )
            if primary and primary.get("presentCount") is not None:
                answered.append(int(primary.get("presentCount") or 0))
        if answered:
            avg_ans = sum(answered) / len(answered)
            pdf.muted(f"Answered avg {_fmt_num(round(avg_ans, 2))} across {len(answered)} questions")

    if questions:
        pdf.section("Per-question report")
        for idx, ctx in enumerate(questions, start=1):
            _render_question_context(pdf, ctx, index=idx)
    elif detail_contexts:
        pdf.section("Contexts")
        for ctx in detail_contexts:
            _render_generic_context(pdf, ctx)
    elif fields:
        pdf.section("Aggregated fields")
        for field in fields:
            if not isinstance(field, dict):
                continue
            pdf.card_start()
            pdf.h3(_safe(field.get("label") or field.get("key") or "Field"))
            _render_facet_distribution(pdf, field)

    if detail_contexts and questions:
        pdf.section("Other contexts")
        for ctx in detail_contexts:
            _render_generic_context(pdf, ctx)

    _render_persona_insights(pdf, contexts)

    if trial_summary and isinstance(trial_summary, dict):
        pdf.section("Run stats")
        facets = trial_summary.get("facets") if isinstance(trial_summary.get("facets"), list) else []
        rows: list[tuple[str, str]] = []
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            label = _safe(facet.get("label") or facet.get("key") or "metric")
            numerical = facet.get("numerical") if isinstance(facet.get("numerical"), dict) else {}
            if numerical:
                rows.append(
                    (
                        label,
                        f"avg {_fmt_num(numerical.get('avg'))} · "
                        f"min {_fmt_num(numerical.get('min'))} · "
                        f"max {_fmt_num(numerical.get('max'))}",
                    )
                )
            else:
                rows.append((label, f"n={_fmt_num(facet.get('presentCount'))}"))
        if rows:
            pdf.kv_block(rows)
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            if isinstance(facet.get("numerical"), dict):
                continue
            pdf.muted(_safe(facet.get("label") or facet.get("key") or "Signal"))
            _render_facet_distribution(pdf, facet, context=trial_summary)
        _render_context_analysis(pdf, trial_summary)

    if trials:
        pdf.section("Trials")
        for trial in trials:
            if not isinstance(trial, dict):
                continue
            persona = trial.get("personaName") or trial.get("personaId") or "-"
            status = "done" if trial.get("completed") else "pending"
            if trial.get("error") or trial.get("succeeded") is False:
                status = "failed"
            name = _safe(trial.get("trialName") or "trial", limit=48)
            line = f"{_safe(persona, limit=28)}  {status}  {name}"
            if trial.get("error"):
                line += f"  · {_safe(trial.get('error'), limit=80)}"
            pdf.ensure_space(6)
            pdf.set_font("Courier", "", 8)
            pdf.set_text_color(30, 41, 59)
            pdf.multi_cell(0, 4, _safe(line, limit=110), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    return bytes(pdf.output())


def _render_persona_dimensions(pdf: _ReportPDF, dims: dict[str, Any]) -> None:
    """Render persona dimensions grouped by category for readability."""
    _CATEGORIES: dict[str, list[str]] = {
        "Demographics": [
            "age_bracket", "gender_identity", "region", "urbanicity",
            "socioeconomic_band", "cultural_background", "life_stage",
        ],
        "Education & Career": [
            "highest_education", "academic_field", "domain", "specialty",
            "seniority_level", "work_sector", "organization_type", "years_experience",
        ],
        "Personality & Cognition": [
            "personality_trait", "risk_appetite", "decision_style", "cognitive_profile",
            "skepticism", "numeracy_comfort", "open_mindedness",
        ],
        "Communication": [
            "primary_language", "multilingualism", "register", "verbosity",
            "formality", "directness", "humor_style", "politeness",
        ],
        "Context & Intent": [
            "current_mood", "goal", "request_type", "trust_level",
            "time_pressure", "interaction_device",
        ],
    }
    categorized: dict[str, list[tuple[str, str]]] = {}
    uncategorized: list[tuple[str, str]] = []

    dim_items = list(dims.items())
    for key, value in dim_items:
        placed = False
        for cat, keys in _CATEGORIES.items():
            if key in keys:
                categorized.setdefault(cat, []).append((_humanize(key), _safe(value)))
                placed = True
                break
        if not placed:
            uncategorized.append((_humanize(key), _safe(value)))

    for cat in _CATEGORIES:
        items = categorized.get(cat)
        if not items:
            continue
        pdf.ensure_space(10)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, _safe(cat), new_x="LMARGIN", new_y="NEXT")
        pdf.kv_block(items)

    if uncategorized:
        pdf.ensure_space(10)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(100, 116, 139)
        pdf.cell(0, 5, "Other", new_x="LMARGIN", new_y="NEXT")
        pdf.kv_block(uncategorized)


def _render_trial_eval_contexts(pdf: _ReportPDF, trial_eval: dict[str, Any]) -> None:
    """Render structured output contexts (task decision, outcome) as labeled cards."""
    contexts = trial_eval.get("contexts") if isinstance(trial_eval.get("contexts"), list) else []
    ignored = {"task_outcome", "user_feedback", "feedback", "persona_alignment"}
    relevant = [c for c in contexts if isinstance(c, dict) and c.get("contextType") not in ignored]
    if not relevant:
        return

    for ctx in relevant:
        pdf.card_start()
        label = ctx.get("label") or ctx.get("key") or "Output"
        pdf.h3(_safe(label, limit=200))
        facets = ctx.get("facets") if isinstance(ctx.get("facets"), list) else []
        rows: list[tuple[str, str]] = []
        long_texts: list[tuple[str, str]] = []
        for facet in facets:
            if not isinstance(facet, dict):
                continue
            f_label = _safe(facet.get("label") or facet.get("key") or "")
            f_value = _safe(facet.get("value") or "", limit=4000)
            if not f_value:
                continue
            if facet.get("role") == "explanation" or len(f_value) > 120:
                long_texts.append((f_label, f_value))
            else:
                rows.append((f_label, f_value))
        if rows:
            pdf.kv_block(rows)
        for lt_label, lt_value in long_texts:
            pdf.muted(lt_label)
            pdf.body(lt_value, size=9)


def build_trial_report_pdf(
    *,
    job_name: str,
    trial_name: str,
    debrief: dict[str, Any],
) -> bytes:
    app_type = str(debrief.get("applicationType") or "chatbot")
    persona = debrief.get("persona") if isinstance(debrief.get("persona"), dict) else {}
    config = debrief.get("config") if isinstance(debrief.get("config"), dict) else {}
    created = debrief.get("createdAt") or ""

    pdf = _ReportPDF()
    pdf.alias_nb_pages()
    pdf.cover(
        eyebrow="Trial report",
        title=_safe(trial_name, limit=120),
        meta_lines=[
            f"Job: {_safe(job_name, limit=120)}",
            f"Application: {_safe(app_type)}",
            f"Created: {_safe(created) or '-'}",
            f"Persona: {_safe(persona.get('name') or persona.get('id') or '-')}",
            f"Task: {_safe(config.get('taskPath') or config.get('applicationId') or '-')}",
        ],
    )

    # ---- Task Context & Instruction ----
    instruction_md = debrief.get("instructionMarkdown") or ""
    context_md = debrief.get("contextMarkdown") or ""
    if context_md or instruction_md:
        pdf.section("Task")
        if context_md:
            pdf.h3("Context")
            for para in context_md.split("\n\n")[:20]:
                text = para.strip()
                if text:
                    pdf.body(text, size=9)
        if instruction_md:
            pdf.h3("Instruction")
            for para in instruction_md.split("\n\n")[:30]:
                text = para.strip()
                if text:
                    pdf.body(text, size=9)

    # ---- Persona ----
    pdf.section("Persona")
    pdf.kv_block(
        [
            ("ID", _safe(persona.get("id"))),
            ("Name", _safe(persona.get("name"))),
            ("Source", _safe(persona.get("source"))),
        ]
    )
    dims = persona.get("dimensions") if isinstance(persona.get("dimensions"), dict) else {}
    if dims:
        _render_persona_dimensions(pdf, dims)

    # ---- Evaluation scorecard ----
    verifier = debrief.get("verifier") if isinstance(debrief.get("verifier"), dict) else {}
    if verifier:
        pdf.section("Evaluation")
        score_pct = ""
        reward = verifier.get("reward")
        if reward is not None:
            try:
                score_pct = f"{int(float(reward) * 100)}%"
            except (ValueError, TypeError):
                score_pct = _fmt_num(reward)
        pdf.metric_strip([
            ("Score", score_pct or _fmt_num(reward)),
            ("Passed", "Yes" if verifier.get("passed") else "No"),
        ])
        if verifier.get("detail"):
            pdf.body(_safe(verifier.get("detail"), limit=800), size=9)

    usage = debrief.get("usage") if isinstance(debrief.get("usage"), dict) else None
    usage_pairs = _usage_metric_pairs(usage)
    if usage_pairs:
        pdf.section("Usage")
        pdf.metric_strip(usage_pairs)

    # ---- Task Output (structured decision from trialEvaluation) ----
    trial_eval = (
        debrief.get("trialEvaluation") if isinstance(debrief.get("trialEvaluation"), dict) else {}
    )
    if trial_eval:
        pdf.section("Task output")
        _render_trial_eval_contexts(pdf, trial_eval)

    # ---- Persona Self-Report (userFeedback) ----
    feedback = (
        debrief.get("userFeedback") if isinstance(debrief.get("userFeedback"), dict) else {}
    )
    if feedback:
        pdf.section("Persona self-report")
        rows: list[tuple[str, str]] = []
        long_texts: list[tuple[str, str]] = []
        for key, value in list(feedback.items())[:25]:
            if key in ("schemaVersion",):
                continue
            k_label = _humanize(key)
            if isinstance(value, (dict, list)):
                long_texts.append((k_label, _safe(value, limit=4000)))
            elif len(str(value)) > 120:
                long_texts.append((k_label, _safe(value, limit=4000)))
            else:
                rows.append((k_label, _safe(value)))
        if rows:
            pdf.kv_block(rows)
        for lt_label, lt_value in long_texts:
            pdf.muted(lt_label)
            pdf.body(lt_value, size=9)

    # ---- App-type specific content ----
    if app_type == "survey":
        survey = debrief.get("surveyResult") if isinstance(debrief.get("surveyResult"), dict) else {}
        instrument = survey.get("instrument") if isinstance(survey.get("instrument"), dict) else {}
        pdf.section("Survey answers")
        pdf.kv_block(
            [
                ("Instrument", _safe(instrument.get("title") or instrument.get("id"))),
                ("Completed", _fmt_num(survey.get("completed"))),
            ]
        )
        answers = survey.get("answers") if isinstance(survey.get("answers"), list) else []
        questions = instrument.get("questions") if isinstance(instrument.get("questions"), list) else []
        labels = {
            str(q.get("id")): q.get("prompt") or q.get("label") or q.get("id")
            for q in questions
            if isinstance(q, dict) and q.get("id") is not None
        }
        for idx, answer in enumerate(answers, start=1):
            if not isinstance(answer, dict):
                continue
            qid = str(answer.get("questionId") or f"q{idx}")
            title = labels.get(qid) or qid
            pdf.card_start()
            pdf.h3(f"Q{idx}. {_safe(title, limit=200)}")
            pdf.body(f"Answer: {_safe(answer.get('value'), limit=500)}", size=9)
            if answer.get("rationale"):
                pdf.body(f"Rationale: {_safe(answer.get('rationale'), limit=600)}", size=9)

    elif app_type == "web":
        web = debrief.get("webResult") if isinstance(debrief.get("webResult"), dict) else {}
        pdf.section("Web result")
        rows = [
            (_safe(key), _safe(web.get(key), limit=240))
            for key in ("selection", "reason", "success", "score", "url")
            if key in web
        ]
        ratings = web.get("ratings") if isinstance(web.get("ratings"), dict) else {}
        rows.extend((_safe(k), _safe(v)) for k, v in list(ratings.items())[:12])
        pdf.kv_block(rows)

    elif app_type == "os-app":
        pass

    else:
        metrics = (
            debrief.get("metricScores") if isinstance(debrief.get("metricScores"), dict) else {}
        )
        if metrics:
            pdf.section("Metric scores")
            pdf.kv_block([(_safe(k), _safe(v)) for k, v in list(metrics.items())[:20]])
        questionnaire = (
            debrief.get("questionnaire") if isinstance(debrief.get("questionnaire"), dict) else {}
        )
        ratings = (
            questionnaire.get("ratings") if isinstance(questionnaire.get("ratings"), dict) else {}
        )
        if ratings:
            pdf.section("Self-report")
            pdf.kv_block([(_safe(k), _safe(v)) for k, v in list(ratings.items())[:20]])
        transcript = debrief.get("transcript") if isinstance(debrief.get("transcript"), list) else []
        if transcript:
            pdf.section("Transcript")
            for turn in transcript[:40]:
                if not isinstance(turn, dict):
                    continue
                role = turn.get("role") or turn.get("speaker") or "turn"
                text = turn.get("content") or turn.get("text") or turn.get("message") or ""
                pdf.body(f"[{_safe(role)}] {_safe(text, limit=700)}", size=9)

    return bytes(pdf.output())


def pdf_filename(*parts: str) -> str:
    cleaned = []
    for part in parts:
        token = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(part).strip())
        token = token.strip("-_") or "report"
        cleaned.append(token[:80])
    return "-".join(cleaned) + ".pdf"
