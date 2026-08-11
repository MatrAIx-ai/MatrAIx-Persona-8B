import type { Locale, MessageBundle } from "../types";

// Each surface owns a separate file under messages/sections. Vite collects
// them automatically, so parallel feature work never needs to edit a shared
// translation table.
const modules = import.meta.glob<MessageBundle>("./sections/*.ts", {
  eager: true,
  import: "default",
});

const dictionaries: Record<Locale, Record<string, string>> = {
  "en-US": {},
  "zh-CN": {},
};

for (const bundle of Object.values(modules)) {
  Object.assign(dictionaries["en-US"], bundle["en-US"] ?? {});
  Object.assign(dictionaries["zh-CN"], bundle["zh-CN"] ?? {});
}

export { dictionaries };
