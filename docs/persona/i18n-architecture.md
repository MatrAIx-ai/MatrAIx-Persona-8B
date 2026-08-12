# Playground i18n Architecture

> Response to the upstream PR review (MatrAIx-ai/MatrAIx-Persona-8B PR #20),
> which asked for four things: (1) a real language dimension — one pack per
> locale, a locale registry, a generic picker, lazy loading, and English
> fallback for missing keys; (2) UI locale decoupled from the runtime/persona
> language; (3) a default that is overridable and recorded — every run persists
> the effective language and its source, and the backend never treats the
> browser locale as authoritative; (4) English-first — en-US is the default and
> source language, other locales are additive packs.

Status: **implemented**. This document describes the shipped architecture.

## 1. Requirements and acceptance criteria

| # | Requirement | Acceptance |
|---|---|---|
| 1 | Independent language dimension | One flat pack per locale (`messages/packs/<code>.ts`); `LOCALE_REGISTRY`; registry-driven picker; lazy loading for every non-English pack; missing keys fall back to English |
| 2 | UI locale vs runtime/persona language decoupled | UI i18n covers chrome only; persona/prompt language is a separate setting (`matraix.personaLanguage`) resolved at launch, never coupled to the UI locale |
| 3 | Overridable default + recorded | Default `follow_ui`; explicit `en`/`ko`/`zh`/`zh-Hant`/`ja`/`pt`/`es` override; every run persists `effective_language` + `language_source` in `persona_meta.json`; backend never reads the browser locale |
| 4 | English-first | `DEFAULT_LOCALE = "en-US"`; en-US is the always-resident source pack; missing keys fall back to it |

## 2. Layout

```
application/playground/frontend/src/i18n/
├── types.ts                 # Locale codes (single source of truth) + LocaleMeta + MessagePack
├── registry.ts              # LOCALE_REGISTRY + per-locale lazy loaders
├── resolve.ts               # Pure resolveMessage()/interpolate() helpers (unit-tested)
├── I18nProvider.tsx         # Lazy provider; en-US resident; startup restore; race guard
├── picker.tsx               # Generic LocalePicker driven by the registry
├── personaLabelKeys.ts      # Pure persona section/dimension id -> i18n key helpers
└── messages/
    └── packs/
        ├── en-US.ts         # Flat single-locale pack (source of truth)
        ├── ko-KR.ts
        ├── zh-CN.ts
        ├── zh-TW.ts
        ├── ja-JP.ts
        ├── pt-BR.ts
        └── es-ES.ts
```

No dual-locale tables anywhere. `messages/sections/*` and the eager
`import.meta.glob` registry were removed.

## 3. Frontend

### 3.1 Locale codes and registry

`LOCALE_REGISTRY` in `registry.ts` is the single source of truth for locale
codes. `Locale` is derived from the registry, while `types.ts` only imports or
re-exports the derived type and shared locale interfaces:

```ts
export const LOCALE_REGISTRY = [
  { code: "en-US", label: "English", englishName: "English" },
  { code: "ko-KR", label: "한국어", englishName: "Korean" },
  { code: "zh-CN", label: "简体中文", englishName: "Simplified Chinese" },
  { code: "zh-TW", label: "繁體中文", englishName: "Traditional Chinese" },
  { code: "ja-JP", label: "日本語", englishName: "Japanese" },
  { code: "pt-BR", label: "Português (Brasil)", englishName: "Brazilian Portuguese" },
  { code: "es-ES", label: "Español", englishName: "Spanish" },
] as const;
export type Locale = (typeof LOCALE_REGISTRY)[number]["code"];
```

Adding a language means adding one registry entry and one locale pack with its
loader. `types.ts` does not contain a second locale-code list.

The shipped packs cover `en-US`, `ko-KR`, `zh-CN`, `zh-TW`, `ja-JP`, `pt-BR`,
and `es-ES`. `zh-TW` uses Traditional Chinese display copy and the canonical
runtime token `zh-Hant`. The five added locale packs keep exact English source
key parity; explicitly documented locale-only self-name keys are allowed.

### 3.2 Provider behavior

- en-US is statically imported and always resident (default + fallback base).
- Other locales are dynamically imported on first switch and cached
  (`packCache`). In-flight requests are tracked **per locale**
  (`inflight: Map<Locale, Promise<MessagePack>>`), so switching locale never
  reuses another locale's pending request.
- On switch, the pack is reset to en-US instantly (consistent fallback) while
  the target pack loads.
- **Startup restore**: if the stored locale is not en-US, its pack is loaded
  on mount, so the picker and the actual UI never disagree.
- **Race guard**: a `requestedRef` tracks the latest requested locale; a stale
  load result (rapid en -> zh-TW -> en switching) is discarded.
- Fallback chain in `t()`: `pack[key] ?? enPack[key] ?? fallback ?? key`.

### 3.3 Missing keys / incomplete community packs

Future optional locale packs may be incomplete; missing keys fall back to English.
The currently shipped seven-locale set is source-key complete for the current
English pack. Tests allow only explicitly documented locale-only extras, so new
source keys cannot silently become English fallback in a shipped pack.

## 4. Runtime / persona language (requirement 3)

Independent of the UI locale:

- Setting: `lib/personaLanguage.ts` — `follow_ui | en | ko | zh | zh-Hant | ja |
  pt | es`, persisted under `matraix.personaLanguage`. `PersonaLanguagePicker`
  generates its options from the UI locale registry and is available in every
  eval cockpit (chatbot, survey, web, OS app).
- Launch: the frontend resolves `follow_ui` against the current UI locale and
  sends explicit `language` (en|ko|zh|zh-Hant|ja|pt|es) + `languageSource`
  (follow_ui|explicit). The legacy `zh` token remains supported for existing
  Simplified Chinese runs; Traditional Chinese is canonicalized as `zh-Hant`.
- Backend: `HarborJobLaunchRequest` validates the pair (an explicit language
  must carry a source; a null language must not claim one) and writes
  `persona_language` / `persona_language_source` into the agent kwargs.
- Rendering: `render_persona_template(language=...)` -> `build_template_
  context_extras`; all persona agents carry the language through system and
  instruction rendering. Precedence: explicit request > env
  `MATRAIX_PERSONA_LANGUAGE` > en.
- Persistence: every run writes `persona_meta.json` with `effective_language`
  and `language_source` (explicit | follow_ui | env | default). The backend
  never reads the browser locale.

## 5. Tests

`src/i18n/__tests__/i18n.test.ts` (vitest, `npm test`): fallback chain,
interpolate, parameterized seven-locale registry/lazy-loader checks, exact
English key parity for the five added packs, new source-key placeholders, runtime
language mapping, and persona label key helpers. Python focused suites cover all
six non-English persona schema packs (1,290 dimensions each), template chrome,
request validation, job persistence, and debrief reconstruction.

## 6. Risks and compatibility

- **en fallback**: `pack[key] ?? enPack[key] ?? fallback` never renders blank;
  only en-US must be complete.
- **Bundle**: ko-KR, zh-CN, zh-TW, ja-JP, pt-BR, and es-ES ship as separate lazy
  chunks (verified in `vite build` output); the main bundle carries en-US only.
- **Compat**: `useI18n` signature unchanged (`locale/setLocale/locales/t/
  formatNumber/formatDate`); the old binary `toggleLocale` was removed with its
  only consumer (TopBar now uses `LocalePicker`).
