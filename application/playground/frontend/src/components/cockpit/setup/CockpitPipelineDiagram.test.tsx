// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { translate } = vi.hoisted(() => ({
  translate: vi.fn((key: string) => `localized:${key}`),
}));

vi.mock("@/i18n/I18nProvider", () => ({
  useI18n: () => ({ t: translate }),
}));

import { CockpitPipelineDiagram } from "./CockpitPipelineDiagram";

class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", ResizeObserverStub);
  translate.mockClear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CockpitPipelineDiagram", () => {
  it("localizes generic system-under-test fallbacks without changing explicit product labels", () => {
    render(
      <CockpitPipelineDiagram
        taskType="chatbot"
        hasPersona
        hasTask
      />,
    );

    expect(
      screen.getByText("localized:cockpitSetup.pipeline.systemUnderTest"),
    ).toBeTruthy();
    expect(translate).toHaveBeenCalledWith(
      "cockpitSetup.pipeline.systemUnderTest",
    );

    cleanup();
    translate.mockClear();

    render(
      <CockpitPipelineDiagram taskType="web" hasPersona hasTask />,
    );

    expect(
      screen.getByText("localized:cockpitSetup.pipeline.systemUnderTest"),
    ).toBeTruthy();
    expect(translate).toHaveBeenCalledWith(
      "cockpitSetup.pipeline.systemUnderTest",
    );

    cleanup();
    translate.mockClear();

    render(
      <CockpitPipelineDiagram
        taskType="chatbot"
        chatbotLabel="Acme Voice Coach"
        hasPersona
        hasTask
      />,
    );

    expect(screen.getByText("Acme Voice Coach")).toBeTruthy();
    expect(
      screen.queryByText("localized:cockpitSetup.pipeline.systemUnderTest"),
    ).toBeNull();
  });
});
