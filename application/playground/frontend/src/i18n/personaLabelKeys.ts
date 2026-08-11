/**
 * Pure i18n-key helpers for persona display labels (no message tables).
 * These map persona section/dimension identifiers to i18n keys; the keys are
 * resolved through useI18n(). Kept separate from locale packs so the packs
 * stay pure data.
 */

function normalizeLabel(value: string | undefined): string {
  return (value ?? "")
    .trim()
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[\/_-]+/g, " ")
    .replace(/\s+/g, " ");
}

const SECTION_KEYS: Record<string, string> = {
  background: "personaDisplay.section.background",
  demographics: "personaDisplay.section.demographics",
  language: "personaDisplay.section.language",
  education: "personaDisplay.section.education",
  career: "personaDisplay.section.career",
  psychology: "personaDisplay.section.psychology",
  capability: "personaDisplay.section.capability",
  "behavior and interaction": "personaDisplay.section.behaviorInteraction",
  "lifestyle and health": "personaDisplay.section.lifestyleHealth",
};

const DIMENSION_KEYS: Record<string, string> = {
  age: "personaDisplay.dimension.age",
  age_bracket: "personaDisplay.dimension.age",
  "age bracket": "personaDisplay.dimension.age",
  region: "personaDisplay.dimension.region",
  domain: "personaDisplay.dimension.domain",
  intent: "personaDisplay.dimension.intent",
  life_stage: "personaDisplay.dimension.lifeStage",
  "life stage": "personaDisplay.dimension.lifeStage",
  source: "personaDisplay.dimension.source",
  gender: "personaDisplay.dimension.gender",
};

function knownKey(map: Record<string, string>, id?: string, label?: string): string | undefined {
  return map[normalizeLabel(id)] ?? map[normalizeLabel(label)];
}

export function personaSectionLabelKey(id?: string, label?: string): string | undefined {
  return knownKey(SECTION_KEYS, id, label);
}

export function personaDimensionLabelKey(id?: string, label?: string): string | undefined {
  return knownKey(DIMENSION_KEYS, id, label);
}
