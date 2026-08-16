import { createIntl, createIntlCache } from "react-intl";
import { describe, expect, it } from "vitest";

import { SOURCE_MESSAGES } from "@/i18n/source";
import type { PersonaPoolCatalog } from "../types";
import {
  classifyPersonaPoolSampleError,
  personaPoolEmptyState,
} from "../personaPoolCopy";

describe("persona-pool presentation state", () => {
  it("preserves a backend coverage error and exposes a stable UI code", () => {
    const raw =
      "Incomplete stratify coverage: 'life_stage=Early career' has 0, need sample_size_per_value_group=1.";

    expect(classifyPersonaPoolSampleError(raw)).toEqual({
      code: "persona_pool_coverage",
      rawMessage: raw,
      showRecoveryHint: true,
    });
  });

  it("keeps the pool identifier as data and lets the English ICU catalog form the empty sentence", () => {
    const state = personaPoolEmptyState({
      pool: "persona/datasets/matraix-persona-dev-sample",
    } as PersonaPoolCatalog);
    const intl = createIntl(
      { locale: "en-US", messages: SOURCE_MESSAGES },
      createIntlCache(),
    );

    expect(state).toEqual({
      code: "persona_pool_empty",
      pool: "matraix persona dev sample",
    });
    expect(
      intl.formatMessage(
        { id: "catalog.personaStore.emptyPool" },
        { pool: state.pool },
      ),
    ).toBe("matraix persona dev sample is empty or could not be loaded.");
  });
});
