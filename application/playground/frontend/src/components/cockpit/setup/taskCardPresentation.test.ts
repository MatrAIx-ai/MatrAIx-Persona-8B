import { describe, expect, it } from "vitest";

import { chatbotEvalTaskCards } from "./cockpitTaskCards";
import {
  taskRuntimeStatusLabel,
  taskTransportLabel,
} from "./taskCardPresentation";
import { taskCardTagLabel, taskCardTags } from "./taskCardLabels";
import type { ChatbotEvalTask } from "@/lib/types";

describe("task card protocol presentation", () => {
  it("renders a structured transport with the active translator", () => {
    const t = (key: string) => {
      expect(key).toBe("cockpitSetup.transport.apiSidecar");
      return "API（本地服务）";
    };

    expect(taskTransportLabel("api_sidecar", t)).toBe("API（本地服务）");
  });
});

describe("task card kind presentation", () => {
  it("keeps the task kind structured until the renderer translates it", () => {
    const [kindTag] = taskCardTags({
      taskPath: "application/tasks/example-product-feedback",
    });

    expect(kindTag).toEqual({ taskKind: "example", tone: "neutral" });
    expect(
      taskCardTagLabel(kindTag, (key: string) => {
        expect(key).toBe("cockpitSetup.taskKind.example");
        return "示例";
      }),
    ).toBe("示例");
  });
});

describe("task card runtime status presentation", () => {
  it("keeps a sidecar-started status structured until the renderer translates it", () => {
    const task: ChatbotEvalTask = {
      id: "support-chat",
      title: "Support chat",
      description: "A support evaluation task.",
      taskPath: "application/tasks/support-chat",
      transport: "mcp",
      applicationId: "support",
      applicationContext: "test",
      defaultDomain: "support",
      metaType: "chatbot",
      domain: "support",
      difficulty: "easy",
      available: false,
    };
    const [card] = chatbotEvalTaskCards([task], {
      runningTaskIds: new Set([task.id]),
    });

    expect(card.runtimeStatus).toBe("sidecar_started");
    expect(card.statusDetail).toBeUndefined();
    expect(
      taskRuntimeStatusLabel(card.runtimeStatus, (key: string) => {
        expect(key).toBe("cockpitSetup.status.sidecarStartedForRun");
        return "此运行的本地服务已启动。";
      }),
    ).toBe("此运行的本地服务已启动。");
  });
});
