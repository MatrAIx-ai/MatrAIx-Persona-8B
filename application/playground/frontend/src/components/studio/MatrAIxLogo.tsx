import { FOCUS_RING } from "../cockpit/cockpitShared";
import { useI18n } from "@/i18n/I18nProvider";

export interface MatrAIxLogoProps {
  /** Pixel size for the wordmark (font-size). */
  size?: "sm" | "md" | "lg";
  /** When set, the logo is a button that navigates home. */
  onClick?: () => void;
  className?: string;
}

const SIZE_CLASS: Record<NonNullable<MatrAIxLogoProps["size"]>, string> = {
  sm: "text-[18px]",
  md: "text-[20px]",
  lg: "text-[30px]",
};

export function MatrAIxLogo({ size = "md", onClick, className = "" }: MatrAIxLogoProps) {
  const { t } = useI18n();
  const wordmark = (
    <span
      className={`whitespace-nowrap font-display font-bold tracking-tight text-text-main ${SIZE_CLASS[size]} ${className}`}
    >
      Matr<span className="text-primary">AI</span>x
    </span>
  );

  if (!onClick) return wordmark;

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={t("misc.logoHomeAria", "MatrAIx home")}
      className={`transition hover:opacity-90 active:scale-[0.97] ${FOCUS_RING}`}
    >
      {wordmark}
    </button>
  );
}
