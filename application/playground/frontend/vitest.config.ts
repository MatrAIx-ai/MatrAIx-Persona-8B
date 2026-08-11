import { mergeConfig } from "vite";
import { defineConfig } from "vitest/config";
import viteConfig from "./vite.config";

/**
 * Vitest config for the Playground frontend.
 *
 * Reuses the app's Vite config (path alias, plugins) via mergeConfig and adds
 * the test runner settings. Tests run in the `node` environment — the i18n
 * layer is pure TS (dynamic `import()` of locale packs works fine under
 * Vitest). Only `*.test.ts` files under `src/` are collected.
 */
export default mergeConfig(
  viteConfig,
  defineConfig({
    test: {
      environment: "node",
      include: ["src/**/*.test.ts"],
      // The Playground app tests nothing in the browser; keep this fast and
      // free of DOM shims.
      globals: false,
      cache: false,
    },
  }),
);
