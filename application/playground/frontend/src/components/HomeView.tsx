import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { CosmicField } from "./studio/CosmicField";
import { DigitalGlobe } from "./studio/DigitalGlobe";
import { useI18n } from "@/i18n/I18nProvider";

export interface HomeViewProps {
  onOpenPlayground: () => void;
}

/**
 * Home hero — digital-twin Earth (persona cloud) on a dark stage.
 * Keeps MatrAIx copy; no floating glass dashboard widgets.
 */
export function HomeView({ onOpenPlayground }: HomeViewProps) {
  const { t } = useI18n();

  return (
    <div className="landing-home-stage relative flex min-h-0 flex-1 flex-col overflow-hidden">
      <CosmicField />
      <div className="custom-scrollbar relative z-[1] flex min-h-0 flex-1 flex-col items-center justify-center px-6 py-10">
        <div className="landing-home-hero landing-fade-up mx-auto flex w-full max-w-[560px] flex-col items-center text-center">
          <div className="landing-home-globe mb-2" aria-hidden>
            <DigitalGlobe />
          </div>

          <div className="landing-stat-block mt-2 items-center">
            <span className="landing-stat-value landing-stat-value--home">8.3B</span>
            <span className="landing-stat-label">{t("shell.home.personas", "personas")}</span>
          </div>

          <h1 className="landing-home-title mt-5">
            {t("shell.home.title", "Planetary-scale")}{" "}
            <span className="landing-home-title-accent">
              {t("shell.home.titleAccent", "digital humans")}
            </span>
          </h1>

          <p className="landing-home-subtitle mt-4 max-w-md text-[14px] leading-relaxed">
            {t(
              "shell.home.subtitle",
              "Simulate real users across chatbots, surveys, browsers, and agents with evaluation reporting",
            )}
          </p>

          <button
            type="button"
            onClick={onOpenPlayground}
            className={`landing-cta-primary mt-8 ${FOCUS_RING}`}
          >
            {t("shell.nav.playground", "Playground")}
            <Sym name="arrow_forward" size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default HomeView;
