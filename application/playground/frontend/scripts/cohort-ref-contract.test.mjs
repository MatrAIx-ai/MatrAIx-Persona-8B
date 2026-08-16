/**
 * Contract checks for cohort-ref frontend helpers (no vitest runner in package).
 * Run: node --test application/playground/frontend/scripts/cohort-ref-contract.test.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function read(rel) {
  return readFileSync(join(root, rel), "utf8");
}

test("PERSONA_UI_ID_LIST_MAX is 100", () => {
  const types = read("src/lib/types.ts");
  assert.match(types, /export const PERSONA_UI_ID_LIST_MAX = 100/);
});

test("Save as dataset is offered for both 1M and dev sample launch caches", () => {
  const rail = read("src/components/cockpit/setup/PersonaSamplingRail.tsx");
  const messages = JSON.parse(read("src/i18n/messages/en-US.json"));
  assert.match(rail, /isMaterializedCohortPool/);
  assert.match(rail, /isGeneratedDevPool/);
  assert.match(rail, /parentDatasetFromCohortPool/);
  assert.match(rail, /canSaveAsDataset/);
  assert.match(rail, /t\("personaSetup\.synthesize"\)/);
  assert.equal(messages["personaSetup.synthesize"], "Synthesize to fill this task");
});

test("storage persists selectedCount / useEntirePool without giant ID arrays", () => {
  const storage = read("src/components/cockpit/setup/cockpitPersonaSetupStorage.ts");
  assert.match(storage, /selectedCount/);
  assert.match(storage, /useEntirePool/);
  assert.match(storage, /PERSONA_UI_ID_LIST_MAX/);
  assert.match(storage, /cohorts\\\/cohort-/);
});

test("launch helper omits personaIds when useEntirePool", () => {
  const launch = read("src/components/cockpit/setup/personaLaunchFields.ts");
  assert.match(launch, /useEntirePool:\s*true/);
  assert.match(launch, /personaIds:\s*input\.selectedPersonaIds/);
});

test("parallel trials are not hard-capped by task type", () => {
  assert.throws(() => read("src/components/cockpit/setup/cockpitParallelCaps.ts"), /ENOENT/);
  const bar = read("src/components/cockpit/setup/RunLaunchBar.tsx");
  assert.doesNotMatch(bar, /parallelCap/);
  assert.match(bar, /const parallelMax = Math\.max\(1, personaCount\)/);
});

test("batch status labels are translated at render time", () => {
  const grid = read("src/components/cockpit/setup/BatchTrialGrid.tsx");
  const mosaic = read("src/components/cockpit/setup/BatchMosaicCanvas.tsx");

  assert.doesNotMatch(grid, /statusLabel:\s*formatBatchCellStatusLabel/);
  assert.match(grid, /formatBatchCellStatusLabel\([\s\S]*?trial\.statusStage[\s\S]*?t,/);
  assert.match(mosaic, /formatBatchCellStatusLabel\([\s\S]*?trial\.statusStage[\s\S]*?t,/);
});

for (const [name, file, key] of [
  ["OS app", "src/components/cockpit/OsAppEvalCockpit.tsx", "eval.os.progress.complete"],
  ["survey", "src/components/cockpit/SurveyEvalCockpit.tsx", "eval.survey.progress.complete"],
  ["web", "src/components/cockpit/WebEvalCockpit.tsx", "eval.web.progress.complete"],
]) {
  test(`${name} completion copy has no missing ICU unit parameter`, () => {
    const source = read(file);
    const messages = JSON.parse(read("src/i18n/messages/en-US.json"));
    assert.match(source, new RegExp(`t\\(\"${key.replaceAll(".", "\\.")}\", \\{ count:`));
    assert.doesNotMatch(messages[key], /\{unit\}/);
    assert.match(messages[key], /\{count, plural,/);
  });
}

test("artifact paths stay inside complete rich messages", () => {
  const runs = read("src/components/RunsView.tsx");
  const debrief = read("src/components/ChatTrialDebrief.tsx");
  const messages = JSON.parse(read("src/i18n/messages/en-US.json"));

  assert.match(runs, /rich\("runs\.jobsSubtitle"/);
  assert.match(debrief, /rich\("runs\.noPersonaSelfReport"/);
  assert.match(messages["runs.jobsSubtitle"], /<path>jobs\/<\/path>/);
  assert.match(messages["runs.noPersonaSelfReport"], /<path>user_feedback\.json<\/path>/);
  assert.equal(messages["runs.jobsSubtitle.beforePath"], undefined);
  assert.equal(messages["runs.noPersonaSelfReport.beforePath"], undefined);
});

test("batch progress, completion, and cancellation copy uses the active locale", () => {
  const hook = read("src/components/cockpit/setup/useCockpitBatchJob.ts");
  const messages = JSON.parse(read("src/i18n/messages/en-US.json"));
  const cockpits = [
    "src/components/cockpit/PlaygroundCockpit.tsx",
    "src/components/cockpit/OsAppEvalCockpit.tsx",
    "src/components/cockpit/SurveyEvalCockpit.tsx",
    "src/components/cockpit/WebEvalCockpit.tsx",
  ].map(read);

  assert.doesNotMatch(hook, /Batch stopped\. Reset|All \$\{total\}|Everyone finished/);
  assert.ok(
    cockpits.every((source) => /formatBatchProgressLabel\(\s*t,/.test(source)),
  );
  assert.ok(cockpits.every((source) => source.includes('t("eval.progress.batchCompleteHint")')));
  assert.ok(cockpits.every((source) => source.includes('t("eval.progress.batchStoppedReset")')));
  assert.match(messages["eval.progress.batchFinished"], /\{total, plural,/);
  assert.match(messages["eval.progress.batchAllFinished"], /\{total, plural,/);
});

test("all four cockpits localize stable client run errors at the view boundary", () => {
  const cockpits = [
    "src/components/cockpit/PlaygroundCockpit.tsx",
    "src/components/cockpit/OsAppEvalCockpit.tsx",
    "src/components/cockpit/SurveyEvalCockpit.tsx",
    "src/components/cockpit/WebEvalCockpit.tsx",
  ].map(read);

  assert.ok(
    cockpits.every(
      (source) =>
        source.includes("classifyCockpitRunError") &&
        source.includes("localizeCockpitRunError"),
    ),
  );
});
