/**
 * TopBar: MatrAIx application header.
 *
 * Nav (centered pill): Persona World · Task Gallery · Home · Playground · Runs.
 * Equal-width slots keep Home visually centered despite uneven label lengths.
 */
import { PreflightChip } from "./PreflightChip";
import { FOCUS_RING, Sym } from "./cockpit/cockpitShared";
import { MatrAIxLogo } from "./studio/MatrAIxLogo";
import { useTheme } from "@/hooks/useTheme";
import { useI18n } from "@/i18n/I18nProvider";
import { LocalePicker } from "@/i18n/picker";

export type StudioMode = "home" | "playground";

export interface TopBarProps {
  mode: StudioMode;
  onModeChange: (mode: StudioMode) => void;
  runsActive: boolean;
  galleryActive: boolean;
  storeActive: boolean;
  onOpenHome: () => void;
  onOpenRuns: () => void;
  onOpenTaskGallery: () => void;
  onOpenPersonaStore: () => void;
  /** "glass" floats over the Home stage as a NASA-panel frosted bar. */
  variant?: "solid" | "glass";
}

export function TopBar({
  mode,
  onModeChange,
  runsActive,
  galleryActive,
  storeActive,
  onOpenHome,
  onOpenRuns,
  onOpenTaskGallery,
  onOpenPersonaStore,
  variant = "solid",
}: TopBarProps) {
  const { theme, toggle } = useTheme();
  const { t } = useI18n();
  const nextIsLight = theme === "dark";
  const overlayActive = runsActive || galleryActive || storeActive;

  const nav: Array<{ key: string; label: string; active: boolean; onClick: () => void }> = [
    {
      key: "store",
      label: t("shell.nav.personaWorld", "Persona World"),
      active: storeActive,
      onClick: onOpenPersonaStore,
    },
    {
      key: "gallery",
      label: t("shell.nav.taskGallery", "Task Gallery"),
      active: galleryActive,
      onClick: onOpenTaskGallery,
    },
    {
      key: "home",
      label: t("shell.nav.home", "Home"),
      active: mode === "home" && !overlayActive,
      onClick: onOpenHome,
    },
    {
      key: "playground",
      label: t("shell.nav.playground", "Playground"),
      active: mode === "playground" && !overlayActive,
      onClick: () => onModeChange("playground"),
    },
    {
      key: "runs",
      label: t("shell.nav.runs", "Runs"),
      active: runsActive,
      onClick: onOpenRuns,
    },
  ];

  const glass = variant === "glass";

  return (
    <header
      className={`nasa-glass-bar z-20 flex-shrink-0 ${
        glass ? "absolute inset-x-0 top-0" : "relative"
      }`}
    >
      <div className="grid h-14 grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 px-5">
        <div className="flex min-w-0 items-center justify-start">
          <MatrAIxLogo size="md" onClick={onOpenHome} />
        </div>

        <nav
          className="nasa-glass-pill hidden items-center rounded-full p-1 backdrop-blur md:flex"
          aria-label={t("shell.nav.application", "Application")}
        >
          <div className="grid grid-cols-5 items-center">
            {nav.map(({ key, label, active, onClick }) => (
              <button
                key={key}
                type="button"
                onClick={onClick}
                aria-current={active ? "page" : undefined}
                title={label}
                className={`flex h-9 min-w-[7.25rem] items-center justify-center rounded-full px-3 text-[13px] font-semibold tracking-[-0.01em] transition ${FOCUS_RING} ${
                  active
                    ? "bg-primary text-on-primary shadow-sm"
                    : "text-text-variant hover:bg-surface-high/70 hover:text-text-main"
                }`}
              >
                <span className="truncate">{label}</span>
              </button>
            ))}
          </div>
        </nav>

        <div className="flex flex-shrink-0 items-center justify-end gap-2.5">
          <PreflightChip />

          <LocalePicker compact />

          <button
            type="button"
            onClick={toggle}
            aria-label={
              nextIsLight
                ? t("shell.theme.switchToLight", "Switch to light theme")
                : t("shell.theme.switchToDark", "Switch to dark theme")
            }
            title={t("shell.theme.toggle", "Toggle light / dark")}
            className={`nasa-glass-pill grid h-9 w-9 flex-none place-items-center rounded-full text-text-variant transition hover:bg-surface-high/40 hover:text-text-main active:scale-95 ${FOCUS_RING}`}
          >
            <Sym name={nextIsLight ? "light_mode" : "dark_mode"} size={18} />
          </button>
        </div>
      </div>
    </header>
  );
}