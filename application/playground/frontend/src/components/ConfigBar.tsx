/**
 * ConfigBar: the Chat workbench's editable config knobs in the top bar.
 *
 * Driven by the enriched config metadata from `GET /api/config/options`: each
 * editable knob carries a human `label`, per-value `{label, description}`, and a
 * `rebuildsAgent` flag. The bar renders one `KnobSelect` per knob (reusing the
 * cockpit's keyboard-operable listbox, which shows the option descriptions), and
 * a small "re-warms on change" warning sits beside any knob whose change
 * cold-starts the cached agent (a slower next turn).
 *
 * Knobs are disabled (read-only) until a session exists, and while a config
 * mutation is in flight, so a knob can't be changed mid-turn-setup.
 */
import { useI18n } from "@/i18n/I18nProvider";
import { KnobSelect, type KnobOption } from "./cockpit/KnobSelect";
import { Sym } from "./cockpit/cockpitShared";
import type { ConfigKnob, SessionConfig } from "@/lib/types";

/**
 * Allowed values per config key: the flat fallback map the bar can still
 * consume when only values (no metadata) are available. App derives the richer
 * `knobs` list directly now, so this is the degraded path.
 */
export type ConfigOptionsMap = Partial<Record<keyof SessionConfig, string[]>>;

/** Humanize a knob key as a fallback label when metadata is absent. */
const FALLBACK_LABEL: Record<string, string> = {
  engine: "Model",
  rankerMode: "Ranker",
  resourceMode: "Resources",
  domain: "Domain",
  botType: "Bot",
};

/** Number of placeholder pills to show while the knob metadata loads. */
const PLACEHOLDER_COUNT = 3;

export interface ConfigBarProps {
  /** Current session config; `null` before a session is selected. */
  config: SessionConfig | null;
  /**
   * The editable config knobs (with labels/descriptions/`rebuildsAgent`) from
   * `/api/config/options`, OR (degraded) the flat value map. `null` until the
   * options query resolves.
   */
  options: ConfigKnob[] | ConfigOptionsMap | null;
  /** Disable all knobs (no session, or a mutation is in flight). */
  disabled?: boolean;
  /** Fired with the changed key/value when the operator picks a new option. */
  onChange: (patch: Partial<SessionConfig>) => void;
}

/** Normalize the `options` prop into the rich knob list (synthesizing from a flat map). */
function toKnobs(options: ConfigBarProps["options"]): ConfigKnob[] | null {
  if (!options) return null;
  if (Array.isArray(options)) return options;
  // Degraded: synthesize bare knobs from the flat value map.
  return Object.entries(options).map(([key, values]) => ({
    key,
    label: FALLBACK_LABEL[key] ?? key,
    description: "",
    options: (values ?? []).map((v) => ({ value: v, label: v, description: "" })),
    rebuildsAgent: false,
  }));
}

export function ConfigBar({ config, options, disabled, onChange }: ConfigBarProps) {
  const { t } = useI18n();
  const knobs = toKnobs(options);

  if (!config || !knobs) {
    // Quiet placeholder pills so the bar keeps its shape while loading.
    return (
      <div className="flex items-center gap-md" aria-hidden>
        {Array.from({ length: PLACEHOLDER_COUNT }).map((_, i) => (
          <div key={i} className="flex items-center gap-2 opacity-50">
            <span className="h-3 w-12 animate-rb-pulse rounded bg-surface-high" />
            <span className="h-7 w-24 animate-rb-pulse rounded bg-surface-high" />
          </div>
        ))}
      </div>
    );
  }

  // Render every editable knob the backend provides, in its display order
  // (engine, domain, …). The fixed ranker/resource modes are not knobs; they
  // live in the Environment facts popover instead.
  return (
    <div className="flex items-center gap-md">
      {knobs.map((knob) => {
        const key = knob.key as keyof SessionConfig;
        const value = config[key];
        if (value === undefined) return null;
        // Domain is owned by each task's chatbot.yaml (black-box). Do not surface
        // the global RecAI catalog knob here.
        if (knob.key === "domain") return null;
        const knobOptions: KnobOption[] = knob.options.map((o) => ({
          value: o.value,
          // Translate only for display; the API value remains the original enum/model id.
          label: t(`cockpit.config.optionLabel.${knob.key}.${o.value}`, o.label),
          description: t(`cockpit.config.optionDescription.${knob.key}.${o.value}`, o.description),
        }));
        return (
          <div key={knob.key} className="flex items-center gap-1.5">
            <KnobSelect
              label={t(`cockpit.config.label.${knob.key}`, knob.label || FALLBACK_LABEL[knob.key] || knob.key)}
              value={String(value)}
              options={knobOptions}
              onChange={(v) => onChange({ [key]: v } as Partial<SessionConfig>)}
              disabled={Boolean(disabled)}
            />
            {knob.rebuildsAgent && (
              <span
                className="flex items-center text-warn"
                title={t(
                  "cockpit.config.rewarm.title",
                  "Changing this re-warms the recommender. The next turn will be slower.",
                )}
                aria-label={t(
                  "cockpit.config.rewarm.aria",
                  "Changing this re-warms the recommender; the next turn will be slower",
                )}
              >
                <Sym name="bolt" fill={1} size={14} />
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}
