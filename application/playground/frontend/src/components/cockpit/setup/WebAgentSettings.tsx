import { useMemo, useState } from "react";

import { useI18n } from "@/i18n/I18nProvider";
import { FOCUS_RING } from "../cockpitShared";
import { CockpitSelect } from "./CockpitSelect";
import {
  defaultWebPersonaAgentForFamily,
  webAgentFamily,
  webPersonaAgentSelectOptions,
  type WebAgentFamily,
} from "@/lib/personaAgentCatalog";

export interface WebAgentSettingsProps {
  taskId: string;
  agentId: string;
  disabled?: boolean;
  onAgentChange: (taskId: string, agentId: string) => void;
}

function FamilyChip({
  active,
  label,
  description,
  onClick,
  disabled,
}: {
  active: boolean;
  label: string;
  description: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`flex min-w-0 flex-1 flex-col rounded-lg px-3 py-2.5 text-left transition ${
        active
          ? "glass-tile glass-tile--active"
          : "glass-tile glass-tile--hover"
      } disabled:cursor-not-allowed disabled:opacity-55 ${FOCUS_RING}`}
    >
      <span
        className={`text-[14px] font-semibold ${active ? "text-primary" : "text-text-main"}`}
      >
        {label}
      </span>
      <span className="mt-0.5 text-[12px] leading-snug text-text-dim">
        {description}
      </span>
    </button>
  );
}

export function WebAgentSettings({
  taskId,
  agentId,
  disabled,
  onAgentChange,
}: WebAgentSettingsProps) {
  const { t } = useI18n();
  const family = webAgentFamily(agentId);
  const [cliConfirmDismissed, setCliConfirmDismissed] = useState(false);
  const harnessOptions = useMemo(
    () => webPersonaAgentSelectOptions(family),
    [family],
  );

  function setFamily(nextFamily: WebAgentFamily) {
    if (nextFamily === family) return;
    if (nextFamily === "cli" && !cliConfirmDismissed) {
      const ok = window.confirm(t("cockpitSetup.web.cliConfirm"));
      if (!ok) return;
      setCliConfirmDismissed(true);
    }
    onAgentChange(taskId, defaultWebPersonaAgentForFamily(nextFamily, taskId));
  }

  return (
    <div className="space-y-3">
      <div>
        <p className="text-[12px] font-semibold uppercase tracking-[0.14em] text-text-dim">
          {t("cockpitSetup.web.agentFamily")}
        </p>
        <div className="mt-2 flex gap-2">
          <FamilyChip
            active={family === "browser"}
            label={t("cockpitSetup.web.browser")}
            description={t("cockpitSetup.web.browserDescription")}
            disabled={disabled}
            onClick={() => setFamily("browser")}
          />
          <FamilyChip
            active={family === "cli"}
            label={t("cockpitSetup.web.cli")}
            description={t("cockpitSetup.web.cliDescription")}
            disabled={disabled}
            onClick={() => setFamily("cli")}
          />
        </div>
      </div>

      <CockpitSelect
        label={t("cockpitSetup.web.harness")}
        value={agentId}
        options={harnessOptions}
        disabled={disabled}
        onChange={(next) => onAgentChange(taskId, next)}
        hint={
          family === "browser"
            ? t("cockpitSetup.web.browserHint")
            : t("cockpitSetup.web.cliHint")
        }
      />
    </div>
  );
}
