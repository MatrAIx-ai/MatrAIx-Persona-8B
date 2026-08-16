import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import test from "node:test";

const checker = join(dirname(fileURLToPath(import.meta.url)), "check-i18n-keys.mjs");

function runChecker(source) {
  const root = mkdtempSync(join(tmpdir(), "matraix-i18n-check-"));
  try {
    mkdirSync(join(root, "src", "i18n", "messages"), { recursive: true });
    writeFileSync(
      join(root, "src", "i18n", "messages", "en-US.json"),
      JSON.stringify({ "status.ready": "Ready", "status.done": "Done" }),
    );
    writeFileSync(join(root, "src", "Sample.tsx"), source);
    return spawnSync(process.execPath, [checker], { cwd: root, encoding: "utf8" });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test("accepts a literal key present in the English source catalog", () => {
  const result = runChecker('const t = (key: string) => key; t("status.ready");');
  assert.equal(result.status, 0, result.stderr);
});

test("rejects a dynamically constructed translation key", () => {
  const result = runChecker(
    'const t = (key: string) => key; const status = "ready"; t(`status.${status}`);',
  );
  assert.equal(result.status, 1);
  assert.match(result.stderr, /translation key must not be dynamically constructed/);
});

test("still validates a literal key wrapped in a type assertion", () => {
  const result = runChecker(
    'const t = (key: string) => key; t("status.missing" as string);',
  );
  assert.equal(result.status, 1);
  assert.match(result.stderr, /missing English key "status.missing"/);
});

test("validates keys passed to the rich-message formatter", () => {
  const result = runChecker(
    'const rich = (key: string) => key; rich("status.missing");',
  );
  assert.equal(result.status, 1);
  assert.match(result.stderr, /missing English key "status.missing"/);
});

test("accepts a key selected from a local explicit message map", () => {
  const result = runChecker(`
    const t = (key: string) => key;
    const STATUS_KEYS = {
      ready: "status.ready",
      done: "status.done",
    } as const;
    const status: keyof typeof STATUS_KEYS = "ready";
    t(STATUS_KEYS[status]);
  `);
  assert.equal(result.status, 0, result.stderr);
});

test("rejects an arbitrary identifier as a translation key", () => {
  const result = runChecker(`
    const t = (key: string) => key;
    const key = getKeyFromRuntime();
    t(key);
  `);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /translation key must not be dynamically constructed/);
});
