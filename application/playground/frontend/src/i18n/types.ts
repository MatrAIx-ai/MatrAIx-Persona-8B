import type sourceMessages from "./messages/en-US.json";

/** Keys are derived from the reviewed English JSON catalog. */
export type MessageKey = keyof typeof sourceMessages;

/** Optional locale packs may omit keys; English remains the fallback. */
export type MessageCatalog = Partial<Record<MessageKey, string>>;

export type MessageValues = Record<string, string | number | boolean | Date>;

export type TextDirection = "ltr" | "rtl";
