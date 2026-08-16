/**
 * Schema-driven persona self-report renderer.
 *
 * Renders whatever fields the task authored in ``self_report_schema.yaml`` —
 * no hard-coded OpenBB / RecAI / default chatbot rows.
 */
import {
  SCORE_BAND_CLASS,
  humanizeToken,
  scoreBand,
} from "./cockpit/cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";
import {
  localizedBooleanLabel,
  localizedStructuredChoiceLabel,
  type Translate,
} from "@/lib/localizedDisplayValues";
import type {
  SelfReportSchema,
  SelfReportSchemaField,
  UserFeedbackArtifact,
} from "@/lib/types";

function displayValue(
  value: string | number | boolean | null | undefined,
  t: Translate,
): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return localizedBooleanLabel(value, t);
  if (typeof value === "number") return String(value);
  const text = String(value).trim();
  if (!text) return "—";
  return localizedStructuredChoiceLabel(text, t) ?? humanizeToken(text);
}

function enumTone(value: string): string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "yes" || normalized === "true")
    return "bg-secondary/10 text-secondary";
  if (normalized === "no" || normalized === "false")
    return "bg-danger/10 text-danger";
  if (normalized === "partially" || normalized === "unsure")
    return "bg-warn/10 text-warn";
  return "glass-tile text-text-variant";
}

function feedbackValue(
  feedback: UserFeedbackArtifact | null | undefined,
  key: string,
): string | number | boolean | null | undefined {
  return feedback?.[key];
}

function FieldRow({
  field,
  value,
  explanation,
  t,
}: {
  field: SelfReportSchemaField;
  value: string | number | boolean | null | undefined;
  explanation?: string | null;
  t: Translate;
}) {
  const kind = (field.kind || "string").toLowerCase();
  const max = field.maximum ?? null;
  const isOverall =
    field.key === "overallExperienceRating" ||
    (kind === "integer" &&
      max === 10 &&
      /overall|experience|rating/i.test(field.key));

  if (isOverall && typeof value === "number") {
    const band = scoreBand(value / Math.max(max ?? 10, 1));
    const color = SCORE_BAND_CLASS[band];
    return (
      <div className="rounded-md glass-panel p-4">
        <div className="hud text-[11px] text-text-dim">{field.prompt}</div>
        <div className="mt-1.5 flex items-baseline gap-1.5">
          <span
            className={`font-display text-[32px] font-bold leading-none tabular-nums ${color.text}`}
          >
            {value}
          </span>
          <span className="text-[14px] text-text-dim">/ {max ?? 10}</span>
        </div>
        {explanation ? (
          <p className="mt-2 text-[14px] leading-relaxed text-text-variant">
            {explanation}
          </p>
        ) : null}
      </div>
    );
  }

  if (
    kind === "integer" &&
    typeof value === "number" &&
    max != null &&
    max > 0
  ) {
    const band = scoreBand(value / max);
    const color = SCORE_BAND_CLASS[band];
    const pct = Math.max(0, Math.min(100, (value / max) * 100));
    return (
      <div>
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="text-[14px] font-medium text-text-main">
            {field.prompt}
          </span>
          <span
            className={`font-mono text-[14px] font-bold tabular-nums ${color.text}`}
          >
            {value} / {max}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-field">
          <div className={`h-full ${color.bar}`} style={{ width: `${pct}%` }} />
        </div>
        {explanation ? (
          <p className="mt-1.5 text-[14px] leading-snug text-text-variant">
            {explanation}
          </p>
        ) : null}
      </div>
    );
  }

  if (kind === "enum" || kind === "boolean") {
    const label = displayValue(value, t);
    const tone =
      typeof value === "string"
        ? enumTone(value)
        : typeof value === "boolean"
          ? enumTone(value ? "yes" : "no")
          : "glass-tile text-text-variant";
    return (
      <div>
        <div className="flex items-start justify-between gap-3">
          <span className="text-[14px] font-medium leading-snug text-text-main">
            {field.prompt}
          </span>
          <span
            className={`inline-flex shrink-0 items-center rounded px-2 py-1 hud text-[11px] ${tone}`}
          >
            {label}
          </span>
        </div>
        {explanation ? (
          <p className="mt-1.5 text-[14px] leading-snug text-text-variant">
            {explanation}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div>
      <div className="text-[14px] font-medium text-text-main">
        {field.prompt}
      </div>
      <p className="mt-1.5 text-[14px] leading-relaxed text-text-variant">
        {displayValue(value, t)}
      </p>
      {explanation ? (
        <p className="mt-1.5 text-[14px] leading-snug text-text-variant">
          {explanation}
        </p>
      ) : null}
    </div>
  );
}

export function SchemaSelfReportPanel({
  schema,
  feedback,
}: {
  schema: SelfReportSchema;
  feedback: UserFeedbackArtifact | null | undefined;
}) {
  const { t } = useI18n();
  const fields = schema.fields ?? [];
  const byKey = new Map(fields.map((field) => [field.key, field]));
  const explanations = new Map<string, string>();
  for (const field of fields) {
    if (!field.explains) continue;
    const text = String(feedbackValue(feedback, field.key) ?? "").trim();
    if (text) explanations.set(field.explains, text);
  }

  const measured = fields.filter((field) => !field.explains);
  if (measured.length === 0) {
    return (
      <div className="rounded-md glass-tile glass-tile--dim px-4 py-8 text-center text-[15px] text-text-variant">
        {t("runs.noMeasurableSelfReportFields")}
      </div>
    );
  }

  const overall = measured.find(
    (field) =>
      field.key === "overallExperienceRating" ||
      ((field.kind || "").toLowerCase() === "integer" &&
        field.maximum === 10 &&
        /overall|experience|rating/i.test(field.key)),
  );
  const rest = measured.filter((field) => field.key !== overall?.key);

  return (
    <div className="space-y-4">
      {overall ? (
        <FieldRow
          field={overall}
          value={feedbackValue(feedback, overall.key)}
          explanation={explanations.get(overall.key) ?? null}
          t={t}
        />
      ) : null}
      {rest.length > 0 ? (
        <div className="space-y-4 rounded-md glass-panel p-4">
          {rest.map((field) => (
            <FieldRow
              key={field.key}
              field={byKey.get(field.key) ?? field}
              value={feedbackValue(feedback, field.key)}
              explanation={explanations.get(field.key) ?? null}
              t={t}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default SchemaSelfReportPanel;
