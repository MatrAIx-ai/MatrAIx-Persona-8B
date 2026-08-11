import { PersonaStoreContent } from "./PersonaStoreContent";
import { StudioMeshShell, StudioPageFrame, StudioPageHeader } from "./studio/StudioShell";
import { useI18n } from "@/i18n/I18nProvider";

export interface PersonaStoreViewProps {
  onOpenInPlayground?: (input: { pool: string; personaIds: string[] }) => void;
}

export function PersonaStoreView({ onOpenInPlayground }: PersonaStoreViewProps) {
  const { t } = useI18n();
  return (
    <StudioMeshShell>
      <StudioPageFrame>
        <StudioPageHeader
          eyebrow={t("catalog.personaWorld.eyebrow", "MatrAIx · Persona World")}
          title={t("catalog.personaWorld.title", "Browse personas")}
          subtitle={t(
            "catalog.personaWorld.subtitle",
            "Click a Matches chip to select that whole group, then Open in Playground.",
          )}
        />
        <PersonaStoreContent onOpenInPlayground={onOpenInPlayground} autoFocusSearch />
      </StudioPageFrame>
    </StudioMeshShell>
  );
}

export default PersonaStoreView;
