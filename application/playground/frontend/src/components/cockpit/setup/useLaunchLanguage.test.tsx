// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LOCALE_REGISTRY } from "@/i18n/registry";
import { SOURCE_LOCALE } from "@/i18n/source";
import { useHarborCockpitRun } from "@/lib/useHarborCockpitRun";

const testState = vi.hoisted(() => ({
  locale: "en-US",
  launchHarborJob: vi.fn(),
  getHarborJob: vi.fn(),
  getHarborTrialEvents: vi.fn(),
  getHarborTrialDebrief: vi.fn(),
  deleteHarborJob: vi.fn(),
  setUrlState: vi.fn(),
  setBatchJobName: vi.fn(),
}));

vi.mock("@/i18n/I18nProvider", () => ({
  useI18n: () => ({ locale: testState.locale }),
}));

vi.mock("@/lib/api", () => ({
  api: {
    launchHarborJob: testState.launchHarborJob,
    getHarborJob: testState.getHarborJob,
    getHarborTrialEvents: testState.getHarborTrialEvents,
    getHarborTrialDebrief: testState.getHarborTrialDebrief,
    deleteHarborJob: testState.deleteHarborJob,
  },
  ApiError: class ApiError extends Error {},
}));

vi.mock("@/lib/useUrlState", () => ({
  useUrlState: () => ({
    state: {
      cockpitBatch: null,
      cockpitJob: null,
      cockpitTrial: null,
      pgTask: null,
    },
    setState: testState.setUrlState,
  }),
}));

vi.mock("./useSetupPersonaSampling", () => ({
  useSetupPersonaSampling: () => ({
    personaPool: "validation-subset",
    selectedPersonaIds: ["persona-0001"],
    selectedCount: 1,
    useEntirePool: false,
    parallelTrials: 1,
    seed: 7,
    personaModel: "test-model",
  }),
}));

vi.mock("./useCockpitBatchJob", () => ({
  useCockpitBatchJob: () => ({
    setBatchJobName: testState.setBatchJobName,
  }),
}));

import { useCockpitLaunch } from "./useCockpitLaunch";

const syntheticLocale = {
  code: "zh-CN",
  nativeName: "Simplified Chinese",
  englishName: "Simplified Chinese",
  personaLanguage: "zh-Hans",
  dir: "ltr",
  fallback: SOURCE_LOCALE,
  load: async () => ({}),
} as unknown as (typeof LOCALE_REGISTRY)[number];

const mutableLocaleRegistry = LOCALE_REGISTRY as unknown as Array<
  (typeof LOCALE_REGISTRY)[number]
>;

function expectedLanguage(locale: string) {
  return mutableLocaleRegistry.find((entry) => entry.code === locale)?.personaLanguage ??
    mutableLocaleRegistry.find((entry) => entry.code === SOURCE_LOCALE)?.personaLanguage;
}

const singleRunInput = {
  taskPath: "application/tasks/example-survey_product-feedback",
  personaId: "persona-0001",
  personaModel: "test-model",
  mapDebrief: () => ({ status: "done" }),
};

beforeEach(() => {
  mutableLocaleRegistry.push(syntheticLocale);
  testState.locale = SOURCE_LOCALE;
  testState.launchHarborJob.mockResolvedValue({ jobName: "job-0001" });
  testState.getHarborJob.mockImplementation(() => new Promise(() => {}));
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  const index = mutableLocaleRegistry.findIndex((entry) => entry.code === syntheticLocale.code);
  if (index >= 0) mutableLocaleRegistry.splice(index, 1);
});

describe("single cockpit launch language", () => {
  it("sends the registry personaLanguage and follow_ui in the final request body", async () => {
    const { result } = renderHook(() => useHarborCockpitRun({ taskKind: "survey" }));

    await act(async () => {
      await result.current.run(singleRunInput);
    });

    expect(testState.launchHarborJob).toHaveBeenCalledWith(
      expect.objectContaining({
        taskPath: singleRunInput.taskPath,
        personaIds: [singleRunInput.personaId],
        language: expectedLanguage(SOURCE_LOCALE),
        languageSource: "follow_ui",
      }),
    );
  });

  it("rebuilds the run callback when the UI locale changes", async () => {
    const { result, rerender } = renderHook(() => useHarborCockpitRun({ taskKind: "survey" }));

    await act(async () => {
      await result.current.run(singleRunInput);
    });

    testState.locale = syntheticLocale.code;
    rerender();

    await act(async () => {
      await result.current.run(singleRunInput);
    });

    expect(testState.launchHarborJob).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        language: expectedLanguage(syntheticLocale.code),
        languageSource: "follow_ui",
      }),
    );
  });
});

describe("batch cockpit launch language", () => {
  it("sends the registry personaLanguage and follow_ui in the final request body", async () => {
    const { result } = renderHook(() =>
      useCockpitLaunch(null, "survey", "application/tasks/example-survey_product-feedback"),
    );

    await act(async () => {
      await result.current.launchBatch({
        taskPath: "application/tasks/example-survey_product-feedback",
        taskId: "task-0001",
      });
    });

    expect(testState.launchHarborJob).toHaveBeenCalledWith(
      expect.objectContaining({
        taskPath: "application/tasks/example-survey_product-feedback",
        personaModel: "test-model",
        personaIds: ["persona-0001"],
        language: expectedLanguage(SOURCE_LOCALE),
        languageSource: "follow_ui",
      }),
    );
  });

  it("rebuilds the batch callback when the UI locale changes", async () => {
    const { result, rerender } = renderHook(() =>
      useCockpitLaunch(null, "survey", "application/tasks/example-survey_product-feedback"),
    );

    await act(async () => {
      await result.current.launchBatch({
        taskPath: "application/tasks/example-survey_product-feedback",
        taskId: "task-0001",
      });
    });

    testState.locale = syntheticLocale.code;
    rerender();

    await act(async () => {
      await result.current.launchBatch({
        taskPath: "application/tasks/example-survey_product-feedback",
        taskId: "task-0002",
      });
    });

    expect(testState.launchHarborJob).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        language: expectedLanguage(syntheticLocale.code),
        languageSource: "follow_ui",
      }),
    );
  });
});
