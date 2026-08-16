// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { chatbotEvalTaskCards } from "./cockpitTaskCards";
import { taskAvailabilityPresentation } from "./taskAvailability";
import { TaskSelectionRail, type TaskCardModel } from "./TaskSelectionRail";
import { I18nProvider } from "@/i18n/I18nProvider";
import type { ChatbotEvalTask } from "@/lib/types";

const translations = {
  "cockpitSetup.status.available": "可用",
  "cockpitSetup.status.unavailable": "不可用",
} as const;

afterEach(cleanup);

describe("taskAvailabilityPresentation", () => {
  it("renders a structured availability status through the active translator", () => {
    const t = (key: keyof typeof translations) => translations[key];

    expect(taskAvailabilityPresentation("available", t)).toEqual({
      label: "可用",
      tone: "secondary",
    });
    expect(taskAvailabilityPresentation("unavailable", t)).toEqual({
      label: "不可用",
      tone: "danger",
    });
    expect(taskAvailabilityPresentation(undefined, t)).toBeNull();
  });

  it("keeps a chatbot task's availability structured until a renderer translates it", () => {
    const task: ChatbotEvalTask = {
      id: "support-chat",
      title: "Support chat",
      description: "A support evaluation task.",
      taskPath: "application/tasks/support-chat",
      transport: "external_http",
      applicationId: "support",
      applicationContext: "test",
      defaultDomain: "support",
      metaType: "chatbot",
      domain: "support",
      difficulty: "easy",
      available: true,
    };

    const [card] = chatbotEvalTaskCards([task]);

    expect(card).toMatchObject({
      available: true,
      availabilityStatus: "available",
    });
    expect(card).not.toHaveProperty("statusLabel");
    expect(card.tags?.some((tag) => tag.label === "Available")).toBe(false);
  });

  it("renders a task's availability through useI18n instead of a stored label", () => {
    const card: TaskCardModel = {
      id: "support-chat",
      title: "Support chat",
      taskType: "chatbot",
      taskPath: "application/tasks/support-chat",
      available: true,
      availabilityStatus: "available",
      tags: [],
    };

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      createElement(
        QueryClientProvider,
        { client: queryClient },
        createElement(
          I18nProvider,
          null,
          createElement(TaskSelectionRail, {
            taskType: "chatbot",
            chatTasks: [card],
            surveyTasks: [],
            webTasks: [],
            cuaTasks: [],
            selectedTaskId: card.id,
            onSelectTask: () => {},
            engine: "test-engine",
            onEngineChange: () => {},
            engineOptions: [],
            maxTurns: null,
            onMaxTurnsChange: () => {},
          }),
        ),
      ),
    );

    expect(screen.getByText("Available")).toBeTruthy();
  });
});
