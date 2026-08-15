import sourceMessagesJson from "./messages/en-US.json";
import type { MessageCatalog, MessageKey } from "./types";

export const SOURCE_LOCALE = "en-US" as const;

export const SOURCE_MESSAGES: Readonly<Record<MessageKey, string>> = sourceMessagesJson;

export function withEnglishFallback(messages: MessageCatalog): Record<MessageKey, string> {
  return { ...SOURCE_MESSAGES, ...messages };
}
