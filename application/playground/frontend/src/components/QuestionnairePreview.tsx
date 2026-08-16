/**
 * Human preview of a survey instrument from structured questionnaire.yaml data.
 * Not the agent-facing markdown dump (Construct / Required / choice tables).
 */
import {
  surveyQuestionTypeChipClass,
  surveyQuestionTypeLabel,
} from "@/lib/surveyDisplay";
import type { SurveyInstrument, SurveyQuestion } from "@/lib/types";
import { useI18n } from "@/i18n/I18nProvider";

export interface QuestionnairePreviewProps {
  instrument: SurveyInstrument;
  className?: string;
}

function optionRows(
  question: SurveyQuestion,
): Array<{ id: string; label: string }> {
  if (question.optionDetails && question.optionDetails.length > 0) {
    return question.optionDetails.map((option) => ({
      id: option.id,
      label: option.label?.trim() || option.id,
    }));
  }
  return (question.options ?? []).map((option) => ({
    id: option,
    label: option,
  }));
}

function QuestionCard({
  question,
  index,
}: {
  question: SurveyQuestion;
  index: number;
}) {
  const { t } = useI18n();
  const typeLabel = surveyQuestionTypeLabel(question.type, t);
  const options = optionRows(question);
  const isLikert = question.type === "likert";
  const min = question.minValue ?? 1;
  const max = question.maxValue ?? 5;

  return (
    <article className="rounded-lg border border-outline/40 bg-surface/40 px-3.5 py-3">
      <div className="mb-1.5 flex flex-wrap items-center gap-2">
        <span className="hud text-[11px] text-primary">Q{index + 1}</span>
        <span
          className={`hud rounded border px-1.5 py-0.5 text-[11px] ${surveyQuestionTypeChipClass(question.type)}`}
        >
          {typeLabel}
        </span>
        {question.required === false ? (
          <span className="hud text-[11px] text-text-dim">
            {t("runs.optional")}
          </span>
        ) : null}
      </div>
      <p className="text-[15px] font-medium leading-snug text-text-main">
        {question.prompt}
      </p>

      {isLikert ? (
        <p className="mt-2 font-mono text-[13px] text-text-variant">
          {t("runs.scale", { min, max })}
        </p>
      ) : null}

      {options.length > 0 ? (
        <ul className="mt-2.5 space-y-1.5">
          {options.map((option) => (
            <li
              key={option.id}
              className="rounded-md border border-outline/30 bg-surface/50 px-2.5 py-1.5 text-[14px] leading-relaxed text-text-main"
            >
              <span>{option.label}</span>
              {option.label !== option.id ? (
                <span className="mt-0.5 block font-mono text-[12px] text-text-dim">
                  {option.id}
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      {question.type === "free_text" ? (
        <p className="mt-2 text-[13px] text-text-dim">
          {t("runs.freeTextAnswer")}
        </p>
      ) : null}
    </article>
  );
}

export function QuestionnairePreview({
  instrument,
  className = "",
}: QuestionnairePreviewProps) {
  const { t } = useI18n();
  const questions = instrument.questions ?? [];
  return (
    <div className={`space-y-3 ${className}`}>
      <div>
        <h3 className="font-display text-[15px] font-semibold text-text-main">
          {instrument.title}
        </h3>
        {instrument.description?.trim() ? (
          <p className="mt-1 text-[14px] leading-relaxed text-text-variant">
            {instrument.description}
          </p>
        ) : null}
        <p className="mt-1 hud text-[11px] text-text-dim">
          {t("runs.questionCount", { count: questions.length })}
        </p>
      </div>
      {questions.length === 0 ? (
        <p className="text-[14px] text-text-dim">{t("runs.noQuestions")}</p>
      ) : (
        questions.map((question, index) => (
          <QuestionCard
            key={question.id || `q-${index}`}
            question={question}
            index={index}
          />
        ))
      )}
    </div>
  );
}

export default QuestionnairePreview;
