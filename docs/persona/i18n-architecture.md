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
| 1 | Independent language dimension | One flat pack per locale (`messages/packs/<code>.ts`); `LOCALE_REGISTRY`; generic `LocalePicker`; lazy loading (zh-CN ships as a separate chunk); missing keys fall back to English |
| 2 | UI locale vs runtime/persona language decoupled | UI i18n covers chrome only; persona/prompt language is a separate setting (`matraix.personaLanguage`) resolved at launch, never coupled to the UI locale |
| 3 | Overridable default + recorded | Default `follow_ui`; explicit `en`/`zh` override; every run persists `effective_language` + `language_source` in `persona_meta.json`; backend never reads the browser locale |
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
        └── zh-CN.ts         # Flat single-locale pack (additive; may be incomplete)
```

No dual-locale tables anywhere. `messages/sections/*` and the eager
`import.meta.glob` registry were removed.

## 3. Frontend

### 3.1 Locale codes and registry

`types.ts` is the single source of truth for codes:

```ts
export const LOCALE_CODES = ["en-US", "zh-CN"] as const;
export type Locale = (typeof LOCALE_CODES)[number];
```

Adding a language = add a code here, a pack file, and a `registry.ts` entry.

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
  load result (rapid en -> zh -> en switching) is discarded.
- Fallback chain in `t()`: `pack[key] ?? enPack[key] ?? fallback ?? key`.

### 3.3 Missing keys / incomplete community packs

zh-CN may be incomplete; missing keys fall back to English. The test suite
documents (but does not enforce) the drift, e.g. `[drift] zh-CN missing N of M
en keys`. Only en-US must be complete.

## 4. Runtime / persona language (requirement 3)

Independent of the UI locale:

- Setting: `lib/personaLanguage.ts` — `follow_ui | en | zh`, persisted under
  `matraix.personaLanguage`. `PersonaLanguagePicker` (Follow UI | English |
  简体中文) is available in every eval cockpit (chatbot, survey, web, OS app).
- Launch: the frontend resolves `follow_ui` against the current UI locale and
  sends explicit `language` (en|zh) + `languageSource` (follow_ui|explicit).
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
interpolate, pack integrity (no duplicate keys; zh drift documented), registry
loaders, persona label key helpers.

## 6. Risks and compatibility

- **en fallback**: `pack[key] ?? enPack[key] ?? fallback` never renders blank;
  only en-US must be complete.
- **Bundle**: zh-CN ships as a lazy chunk (verified in `vite build` output),
  the main bundle carries en-US only.
- **Compat**: `useI18n` signature unchanged (`locale/setLocale/locales/t/
  formatNumber/formatDate`); the old binary `toggleLocale` was removed with its
  only consumer (TopBar now uses `LocalePicker`).
