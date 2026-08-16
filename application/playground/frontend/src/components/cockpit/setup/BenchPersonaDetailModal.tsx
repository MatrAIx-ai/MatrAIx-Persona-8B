import { useQuery } from "@tanstack/react-query";

import { Markdown } from "@/components/Markdown";
import { useI18n } from "@/i18n/I18nProvider";
import { api, ApiError } from "@/lib/api";
import { PERSONA_BENCH_POOL, type PersonaPoolPersonaCard } from "@/lib/types";
import { RailInsetModal } from "./RailInsetModal";

export interface BenchPersonaDetailModalProps {
  open: boolean;
  persona: PersonaPoolPersonaCard | null;
  pool?: string | null;
  onClose: () => void;
  onUse?: (persona: PersonaPoolPersonaCard) => void;
}

export function BenchPersonaDetailModal({
  open,
  persona,
  pool = PERSONA_BENCH_POOL,
  onClose,
  onUse,
}: BenchPersonaDetailModalProps) {
  const { t } = useI18n();
  const personaId = persona?.personaId ?? null;
  const activePool = pool?.trim() || PERSONA_BENCH_POOL;
  const detailQuery = useQuery({
    queryKey: ["persona-pool-detail", activePool, personaId],
    queryFn: () => api.getPersonaPoolPersona(personaId!, activePool),
    enabled: open && Boolean(personaId),
    staleTime: 120_000,
    retry: 1,
  });

  const markdown = detailQuery.data?.profileMarkdown?.trim() ?? "";

  return (
    <RailInsetModal
      open={open && Boolean(persona)}
      title={
        persona?.name ??
        (personaId ? `persona-${personaId}` : t("cockpitSetup.persona.title"))
      }
      subtitle={t("cockpitSetup.persona.poolSubtitle", { pool: activePool })}
      onClose={onClose}
    >
      {detailQuery.isPending && (
        <p className="text-[14px] text-text-dim">
          {t("cockpitSetup.persona.loadingRecord")}
        </p>
      )}
      {detailQuery.isError && (
        <p className="text-[14px] text-danger">
          {detailQuery.error instanceof ApiError
            ? detailQuery.error.message
            : t("cockpitSetup.persona.loadRecordFailed")}
        </p>
      )}
      {markdown && (
        <Markdown className="text-[14px] leading-relaxed text-text-variant">
          {markdown}
        </Markdown>
      )}
      {onUse && persona && (
        <div className="mt-4 flex justify-end border-t border-outline/30 pt-4">
          <button
            type="button"
            onClick={() => {
              onUse(persona);
              onClose();
            }}
            className="inline-flex h-9 items-center rounded-md bg-primary px-4 text-[14px] font-medium text-on-primary transition hover:bg-primary/90"
          >
            {t("cockpitSetup.persona.use")}
          </button>
        </div>
      )}
    </RailInsetModal>
  );
}
