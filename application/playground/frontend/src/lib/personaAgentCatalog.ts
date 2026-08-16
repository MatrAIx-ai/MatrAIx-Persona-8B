import type { CockpitSelectOption } from "@/components/cockpit/setup/CockpitSelect";

/** Control surface from light (script-only) → full (desktop pixels). */
export type AgentCapabilityTier = "light" | "standard" | "extended" | "full";

/** Browser-native web agents vs generalist Docker CLI harnesses. */
export type WebAgentFamily = "browser" | "cli";

export interface PersonaAgentOption {
  value: string;
  label: string;
  capability: string;
  tier: AgentCapabilityTier;
  summary: string;
  /** Optional badge in the agent picker (e.g. subscription auth). */
  badge?: string;
}

/** Harbor web agents — increasing control surface. */
export const WEB_PERSONA_AGENTS: PersonaAgentOption[] = [
  {
    value: "persona-openhands-sdk",
    label: "OpenHands SDK",
    capability: "Playwright + DOM",
    tier: "light",
    summary: "the agent writes playwright scripts in a terminal — page structure only, no packaged browser product.",
  },
  {
    value: "persona-browser-use",
    label: "Browser-use",
    capability: "Browser + DOM + Vision",
    tier: "standard",
    summary: "a ready-made website agent — browse and save output inside one chromium loop, no shell.",
  },
  {
    value: "persona-cocoa",
    label: "CocoaAgent",
    capability: "Browser API (incl. vision) + DOM + File + Code",
    tier: "extended",
    summary:
      "browse plus dom tools, files, shell, and code in one sandbox — still inside browser apis, not full-desktop clicks.",
  },
  {
    value: "persona-computer-1",
    label: "Computer-use",
    capability: "Pixel Click full Desktop",
    tier: "full",
    summary: "sees the whole desktop and clicks screen coordinates — for native apps, not structured page apis.",
  },
];

/** Generalist CLI harnesses — optional for web tasks (experimental). */
export const CLI_PERSONA_AGENTS: PersonaAgentOption[] = [
  {
    value: "persona-claude-code",
    label: "Claude Code",
    capability: "Terminal CLI",
    tier: "standard",
    summary: "general-purpose terminal agent in docker — same stack as survey/chat.",
    badge: "Anthropic",
  },
  {
    value: "persona-codex",
    label: "Codex",
    capability: "Terminal CLI",
    tier: "standard",
    summary: "general-purpose terminal agent in docker — same stack as survey/chat.",
    badge: "OpenAI",
  },
  {
    value: "persona-gemini-cli",
    label: "Gemini CLI",
    capability: "Terminal CLI",
    tier: "standard",
    summary: "general-purpose terminal agent in docker — same stack as survey/chat.",
    badge: "Google",
  },
];

/** persona-computer-1 runtime backends for CUA tasks. */
export const CUA_RUNTIME_OPTIONS: PersonaAgentOption[] = [
  {
    value: "docker",
    label: "Docker desktop",
    capability: "Linux Xvfb",
    tier: "standard",
    summary: "linux desktop in docker with xvfb — default for desktop tasks.",
  },
  {
    value: "macos",
    label: "use.computer macOS",
    capability: "Native macOS",
    tier: "full",
    summary: "real macos desktop via use.computer.",
  },
  {
    value: "ios",
    label: "use.computer iOS",
    capability: "iOS Simulator",
    tier: "full",
    summary: "ios simulator via use.computer.",
  },
];

export const USE_COMPUTER_URL = "https://use.computer";

export const WEB_TASK_SUGGESTED_AGENT: Record<string, string> = {
  "web-playwright-quote-choice": "persona-openhands-sdk",
  "web-browser-use-laptop-choice": "persona-browser-use",
  "web-cocoa-plan-choice": "persona-cocoa",
  "web-cua-bookshop-choice": "persona-computer-1",
};

export function webAgentFamily(agentId: string): WebAgentFamily {
  return CLI_PERSONA_AGENTS.some((opt) => opt.value === agentId) ? "cli" : "browser";
}

export function webPersonaAgentsForFamily(family: WebAgentFamily): PersonaAgentOption[] {
  return family === "cli" ? CLI_PERSONA_AGENTS : WEB_PERSONA_AGENTS;
}

export function defaultWebPersonaAgentForFamily(family: WebAgentFamily, taskId?: string): string {
  if (family === "browser") {
    return taskId ? suggestedWebPersonaAgent(taskId) : WEB_PERSONA_AGENTS[0].value;
  }
  return CLI_PERSONA_AGENTS[0].value;
}

function personaAgentToSelectOption(opt: PersonaAgentOption): CockpitSelectOption {
  return {
    value: opt.value,
    label: opt.label,
    meta: opt.badge ? `${opt.badge} · ${opt.capability}` : `${opt.tier} · ${opt.capability}`,
    summary: opt.summary,
    group: webAgentFamily(opt.value) === "cli" ? "CLI agents (experimental)" : "Browser agents",
  };
}

export function webPersonaAgentSelectOptions(family?: WebAgentFamily): CockpitSelectOption[] {
  const agents = family ? webPersonaAgentsForFamily(family) : [...WEB_PERSONA_AGENTS, ...CLI_PERSONA_AGENTS];
  return agents.map(personaAgentToSelectOption);
}

export function webPersonaAgentGroupedSelectOptions(): CockpitSelectOption[] {
  return webPersonaAgentSelectOptions();
}

export function cuaRuntimeSelectOptions(platform: string): CockpitSelectOption[] {
  return cuaRuntimeOptionsForPlatform(platform).map((opt) => ({
    value: opt.value,
    label: opt.label,
    meta: opt.capability,
    summary: opt.summary,
  }));
}

export function suggestedWebPersonaAgent(taskId: string): string {
  return WEB_TASK_SUGGESTED_AGENT[taskId] ?? "persona-openhands-sdk";
}

export function resolveWebPersonaAgent(taskId: string, overrides: Record<string, string>): string {
  return overrides[taskId] ?? suggestedWebPersonaAgent(taskId);
}

export function suggestedCuaBackend(platform: string): string {
  if (platform === "macos") return "macos";
  if (platform === "ios") return "ios";
  return "docker";
}

export function resolveCuaBackend(
  taskId: string,
  platform: string,
  overrides: Record<string, string>,
): string {
  return overrides[taskId] ?? suggestedCuaBackend(platform);
}

export function cuaRuntimeOptionsForPlatform(platform: string): PersonaAgentOption[] {
  if (platform === "macos") {
    return CUA_RUNTIME_OPTIONS.filter((opt) => opt.value === "macos");
  }
  if (platform === "ios") {
    return CUA_RUNTIME_OPTIONS.filter((opt) => opt.value === "ios");
  }
  return CUA_RUNTIME_OPTIONS.filter((opt) => opt.value === "docker");
}

export function findWebPersonaAgent(agentId: string): PersonaAgentOption | undefined {
  return WEB_PERSONA_AGENTS.find((opt) => opt.value === agentId);
}

export function findPersonaAgent(agentId: string): PersonaAgentOption | undefined {
  return findWebPersonaAgent(agentId) ?? CLI_PERSONA_AGENTS.find((opt) => opt.value === agentId);
}

export function webPersonaAgentLabel(agentId: string): string {
  return findPersonaAgent(agentId)?.label ?? agentId;
}

/** Platform-aware persona model list for web runs (harness-specific). */
export function webPersonaModelSelectOptions(
  agentId: string,
  options: CockpitSelectOption[],
): CockpitSelectOption[] {
  if (agentId === "persona-computer-1") {
    return cuaPersonaModelSelectOptions("linux", options);
  }
  if (agentId === "persona-claude-code") {
    return options.filter((opt) => opt.value.startsWith("anthropic/"));
  }
  if (agentId === "persona-codex") {
    return options.filter((opt) => opt.value.startsWith("openai/"));
  }
  if (agentId === "persona-gemini-cli") {
    const google = options.filter(
      (opt) => opt.value.startsWith("google/") || opt.value.startsWith("gemini/"),
    );
    if (google.length > 0) return google;
    return [
      {
        value: "google/gemini-2.5-pro",
        label: "Gemini 2.5 Pro",
        meta: "CLI default (configure in Matraix Playground if unsupported)",
        summary: "Gemini CLI harness expects a Google model id.",
      },
    ];
  }
  return options;
}

const CAPABILITY_TIER_LABELS: Record<AgentCapabilityTier, string> = {
  light: "Light",
  standard: "Standard",
  extended: "Extended",
  full: "Full",
};

export function webHarnessPipelineLabel(agentId: string): string {
  const opt = findPersonaAgent(agentId);
  if (!opt) return agentId;
  if (webAgentFamily(agentId) === "cli") {
    return `${opt.label} · CLI`;
  }
  return `${CAPABILITY_TIER_LABELS[opt.tier]} · ${opt.capability}`;
}

export function webPersonaAgentMode(agentId: string): string {
  return webPersonaAgentLabel(agentId);
}

export function webPersonaAgentCapabilityLabel(agentId: string): string {
  const opt = findPersonaAgent(agentId);
  if (!opt) return agentId;
  return `${opt.label} (${opt.capability})`;
}

/** Capability tier for the web pipeline (no agent naming). */
export function webCapabilityTierLabel(agentId: string): string {
  const tier = findPersonaAgent(agentId)?.tier;
  return tier ? CAPABILITY_TIER_LABELS[tier] : "Per task";
}

/** Short control-surface summary for the web pipeline node detail. */
export function webCapabilitySurfaceLabel(agentId: string): string {
  return findPersonaAgent(agentId)?.capability ?? "per task";
}

export function webCapabilityTierIcon(agentId: string): string {
  const tier = findPersonaAgent(agentId)?.tier;
  return webCapabilityTierIconForTier(tier);
}

export function webCapabilityTierIconForTier(tier?: AgentCapabilityTier | string | null): string {
  switch (tier) {
    case "light":
      return "code";
    case "standard":
      return "language";
    case "extended":
      return "extension";
    case "full":
      return "desktop_windows";
    default:
      return "tune";
  }
}

export interface PipelinePathOption {
  id: string;
  label: string;
  icon: string;
  hint?: string;
}

/** Web access paths — vertical fork before the Website node. */
export const WEB_ACCESS_PIPELINE_PATHS: PipelinePathOption[] = WEB_PERSONA_AGENTS.map((agent) => ({
  id: agent.tier,
  label: CAPABILITY_TIER_LABELS[agent.tier],
  icon: webCapabilityTierIconForTier(agent.tier),
  hint: agent.capability,
}));

/** Chatbot connection paths — vertical fork before the Chatbot node. */
export const CHAT_ACCESS_PIPELINE_PATHS: PipelinePathOption[] = [
  { id: "api_sidecar", label: "API (sidecar)", icon: "dns", hint: "Local compose" },
  { id: "api_external", label: "API (endpoint)", icon: "http", hint: "Upstream URL" },
  { id: "mcp_sidecar", label: "MCP (sidecar)", icon: "hub", hint: "Local compose" },
  { id: "mcp_external", label: "MCP (endpoint)", icon: "hub", hint: "Upstream URL" },
];

export function personaAgentSelectLabel(opt: PersonaAgentOption): string {
  return `${opt.label} (${opt.capability})`;
}

export const OS_APP_TAB_LABEL = "OS app";

/** OS platform paths — vertical fork before the OS app node. */
export const OS_PLATFORM_PIPELINE_PATHS: PipelinePathOption[] = [
  { id: "linux", label: "Linux", icon: "desktop_windows", hint: "Docker · Xvfb" },
  { id: "macos", label: "macOS", icon: "laptop_mac", hint: "use.computer" },
  { id: "ios", label: "iOS", icon: "phone_iphone", hint: "Simulator" },
];

export function cuaRuntimeLabel(backend: string): string {
  const opt = CUA_RUNTIME_OPTIONS.find((o) => o.value === backend);
  return opt ? `${opt.label} (${opt.capability})` : backend;
}

/** Default LLM for OS app Harbor runs (persona-computer-1 ``model_name``). */
export const DEFAULT_CUA_AGENT_MODEL = "anthropic/claude-haiku-4-5";

/** OpenAI models with native computer-use (use.computer OpenAICUAAgent / Harbor Computer1). */
const OPENAI_CUA_MODELS = new Set(["openai/gpt-5.4", "openai/gpt-5.5"]);

function isCuaCapablePersonaModel(modelId: string, platform: string): boolean {
  if (modelId.startsWith("anthropic/")) return true;
  if (platform === "ios") {
    // IOSAgent is litellm-backed and accepts any vision-capable chat model.
    return modelId.startsWith("openai/") || modelId.startsWith("gemini/");
  }
  // macOS / Linux desktop: native CUA providers only.
  return OPENAI_CUA_MODELS.has(modelId) || modelId.startsWith("gemini/");
}

/** Platform-aware agent model list for the Persona rail. */
export function cuaPersonaModelSelectOptions(
  platform: string | undefined,
  options: CockpitSelectOption[],
): CockpitSelectOption[] {
  const normalized = (platform ?? "linux").toLowerCase();
  if (normalized === "macos" || normalized === "ios") {
    return options.filter((opt) => isCuaCapablePersonaModel(opt.value, normalized));
  }
  return options;
}

/** Short pipeline subtitle for the Persona node (mirrors the Persona model selector). */
export function personaModelPipelineLabel(
  modelId: string | undefined,
  options: Pick<CockpitSelectOption, "value" | "label">[],
): string {
  if (!modelId) return "Base model";
  const match = options.find((opt) => opt.value === modelId);
  if (match) return match.label;
  const slash = modelId.lastIndexOf("/");
  return slash >= 0 ? modelId.slice(slash + 1) : modelId;
}
