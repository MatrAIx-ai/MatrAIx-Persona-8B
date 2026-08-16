import type { I18nContextValue } from "@/i18n/I18nProvider";

export type HarborReportTranslate = I18nContextValue["t"];

export type LikertScale = { min: number; max: number };

/** Last segment of a qualified aggregation key (`task_outcome.primary.outcome_status` → `outcome_status`). */
export function facetKeyLeaf(key: string | null | undefined): string {
  const raw = (key ?? "").trim();
  if (!raw) return "";
  const parts = raw.split(".").filter(Boolean);
  return parts[parts.length - 1] ?? raw;
}

function canonicalFacetKey(value: string): string {
  return value.trim().toLowerCase().replace(/[\s-]+/g, "_");
}

function standardFacetLabel(key: string, t: HarborReportTranslate): string | null {
  switch (key) {
    case "outcome_status":
      return t("reports.context.taskOutcome");
    case "outcome_reason":
      return t("reports.facet.whyResult");
    case "feedback_reason":
      return t("reports.facet.whyRated");
    case "clarification_questions_useful":
    case "asked_useful_clarification_questions":
      return t("reports.facet.clarifyingQuestionsUseful");
    case "clarification_usefulness":
      return t("reports.facet.clarificationHelp");
    case "felt_understood":
      return t("reports.facet.feltUnderstood");
    case "conversation_path":
      return t("reports.facet.chatWent");
    case "process_notes":
      return t("reports.facet.chatHappened");
    case "resolution_basis":
      return t("reports.facet.resultJudged");
    case "next_step_owner":
      return t("reports.facet.nextActor");
    case "task_goal_label":
      return t("reports.facet.userGoal");
    case "trust_level":
      return t("reports.facet.trust");
    case "effort_rating":
      return t("reports.facet.effort");
    case "clarity_of_next_step":
      return t("reports.facet.nextStepClear");
    case "user_turn_count":
      return t("reports.facet.userTurns");
    case "assistant_turn_count":
      return t("reports.facet.assistantTurns");
    case "message_count":
      return t("reports.facet.messages");
    case "need_satisfaction":
      return t("reports.facet.needsMet");
    case "clarification_question_count":
      return t("reports.facet.clarifyingQuestions");
    case "policy_compliance":
      return t("reports.facet.policyCheck");
    case "groundedness_primary":
      return t("reports.facet.groundedness");
    case "coordination_mode":
      return t("reports.facet.actor");
    case "guidance_quality":
      return t("reports.facet.guidanceQuality");
    case "state_change_achieved":
      return t("reports.facet.stateChanged");
    case "status":
      return t("reports.context.taskOutcome");
    case "user_action_required":
      return t("reports.facet.userActionNeeded");
    case "goal_completion_bucket":
    case "goal_completion_ratio":
      return t("reports.facet.goalCompletion");
    case "primary_failure_reason":
      return t("reports.facet.mainFailureReason");
    case "verifier_mode":
      return t("reports.facet.checkedHow");
    case "personal_preference_satisfaction":
      return t("reports.facet.preferencesMatched");
    default:
      return null;
  }
}

/**
 * Translate only stable, frontend-owned aggregation metadata. Authored labels,
 * prompts, report prose, and model text remain byte-for-byte unchanged.
 */
export function humanizeFacetLabel(
  label: string | null | undefined,
  key: string | null | undefined,
  t: HarborReportTranslate,
): string {
  const leafKey = facetKeyLeaf(key);
  const labelLooksLikeKey = Boolean(
    label &&
      label.includes(".") &&
      !/\s/.test(label) &&
      /^[a-zA-Z0-9_.-]+$/.test(label),
  );
  const raw = (
    labelLooksLikeKey ? leafKey || label || "" : label ?? (leafKey || key || "")
  ).trim();
  if (!raw) return t("reports.facet.explanation");

  const known = standardFacetLabel(canonicalFacetKey(leafKey), t) ?? standardFacetLabel(canonicalFacetKey(raw), t);
  if (known) return known;

  // Multi-word authored labels are task/report-owned and must not be translated.
  if (label && !labelLooksLikeKey && /\s/.test(label.trim())) return label.trim();

  if (canonicalFacetKey(raw).endsWith("_reason")) {
    const subject = raw.replace(/\s*reason$/i, "").trim() || t("reports.facet.explanation");
    return t("reports.facet.whyLabel", { label: subject });
  }

  // Never surface opaque dotted aggregation keys. The unknown key itself remains data-owned.
  if (labelLooksLikeKey || (/^[a-zA-Z0-9_.-]+$/.test(raw) && raw.includes("."))) {
    const readable = facetKeyLeaf(raw)
      .replace(/[_-]+/g, " ")
      .replace(/\b\w/g, (character) => character.toUpperCase());
    return t("reports.facet.unknownLabel", { label: readable });
  }
  return raw;
}

/** A localized noun phrase for the text dimension in a cross-facet view. */
export function crossFacetReasonPhrase(
  textFacetKey: string | null | undefined,
  t: HarborReportTranslate,
): string {
  switch (canonicalFacetKey(facetKeyLeaf(textFacetKey))) {
    case "outcome_reason":
      return t("reports.analysis.reasonsForResult");
    case "feedback_reason":
      return t("reports.analysis.reasonsForRating");
    case "process_notes":
      return t("reports.facet.chatHappened");
    case "conversation_path":
      return t("reports.facet.chatWent");
    case "resolution_basis":
      return t("reports.facet.resultJudged");
    default: {
      if (!textFacetKey?.trim()) return t("reports.analysis.personaExplanations");
      const label = humanizeFacetLabel(null, textFacetKey, t);
      return label === t("reports.facet.explanation") ? t("reports.analysis.personaExplanations") : label;
    }
  }
}

/**
 * Translate only the standard report-generator titles; authored analysis titles
 * stay as supplied by the report.
 */
export function humanizeAnalysisTitle(
  title: string | null | undefined,
  t: HarborReportTranslate,
): string {
  const raw = (title ?? "").trim();
  if (!raw) return t("reports.analysis.analysis");
  if (/^Outcome reason$/i.test(raw)) return t("reports.facet.whyResult");
  if (/^Feedback reason$/i.test(raw)) return t("reports.facet.whyRated");
  if (/^Process notes$/i.test(raw)) return t("reports.facet.chatHappened");

  const localizeGroup = (value: string) => {
    const group = humanizeFacetLabel(value, canonicalFacetKey(value), t);
    return `${group.charAt(0).toLowerCase()}${group.slice(1)}`;
  };
  const outcomeReason = raw.match(/^Outcome reason by\s+(.+)$/i);
  if (outcomeReason) {
    return t("reports.analysis.whyResultBy", { group: localizeGroup(outcomeReason[1]) });
  }
  const feedbackReason = raw.match(/^Feedback reason by\s+(.+)$/i);
  if (feedbackReason) {
    return t("reports.analysis.whyRatedBy", { group: localizeGroup(feedbackReason[1]) });
  }
  const processNotes = raw.match(/^Process notes by\s+(.+)$/i);
  if (processNotes) {
    return t("reports.analysis.chatWentBy", { group: localizeGroup(processNotes[1]) });
  }
  return raw;
}

export function humanizeAnalysisStatus(
  status: string | null | undefined,
  t: HarborReportTranslate,
): string | undefined {
  const normalized = (status ?? "").trim().toLowerCase();
  if (!normalized) return undefined;
  switch (normalized) {
    case "ready_for_llm":
    case "ready":
      return t("reports.status.waitingToSummarize");
    case "queued":
      return t("reports.status.queued");
    case "running":
      return t("reports.status.summarizing");
    case "pending":
      return t("reports.status.pending");
    case "completed":
    case "done":
      return t("reports.status.ready");
    case "completed_with_errors":
      return t("reports.status.readyWithIssues");
    case "failed":
    case "llm_failed":
      return t("reports.status.failed");
    default:
      return status!.replace(/_/g, " ");
  }
}

export function likertPointLabel(
  value: number,
  scaleLabels: Readonly<Record<string, string>> | null | undefined,
  scale: LikertScale,
  t: HarborReportTranslate,
): string | null {
  const key = String(Math.round(value));
  const custom = scaleLabels?.[key]?.trim();
  if (custom) return custom;
  if (scale.min === 1 && scale.max === 5) {
    switch (key) {
      case "1":
        return t("reports.likert.stronglyDisagree");
      case "2":
        return t("reports.likert.disagree");
      case "3":
        return t("reports.likert.neutral");
      case "4":
        return t("reports.likert.agree");
      case "5":
        return t("reports.likert.stronglyAgree");
      default:
        return null;
    }
  }
  if (value === scale.min) return t("reports.likert.low");
  if (value === scale.max) return t("reports.likert.high");
  return null;
}
