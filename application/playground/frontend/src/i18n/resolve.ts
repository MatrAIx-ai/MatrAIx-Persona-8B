import type { MessagePack, MessageValues } from "./types";

/**
 * Resolve a message key against the active locale pack, falling back to the
 * always-present English pack and finally to an explicit fallback (which
 * defaults to the key itself, matching I18nProvider's previous behavior).
 *
 * Pure function — extracted from I18nProvider so the resolution chain can be
 * unit-tested without a React render.
 */
export function resolveMessage(
  pack: MessagePack,
  enPack: MessagePack,
  key: string,
  fallback?: string,
): string {
  return pack[key] ?? enPack[key] ?? fallback ?? key;
}

/**
 * Replace `{placeholder}` tokens in a template with the given values.
 * Missing placeholders are left untouched; numeric values are stringified.
 */
export function interpolate(template: string, values?: MessageValues): string {
  if (!values) return template;
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    Object.prototype.hasOwnProperty.call(values, key) ? String(values[key]) : match,
  );
}
