export type TaskTransport =
  | "api_sidecar"
  | "api_external"
  | "mcp_sidecar"
  | "mcp_external";

export type TaskRuntimeStatus = "sidecar_started";

type TransportMessageKey =
  | "cockpitSetup.transport.apiSidecar"
  | "cockpitSetup.transport.apiEndpoint"
  | "cockpitSetup.transport.mcpSidecar"
  | "cockpitSetup.transport.mcpEndpoint";

const TRANSPORT_MESSAGE_KEYS: Record<TaskTransport, TransportMessageKey> = {
  api_sidecar: "cockpitSetup.transport.apiSidecar",
  api_external: "cockpitSetup.transport.apiEndpoint",
  mcp_sidecar: "cockpitSetup.transport.mcpSidecar",
  mcp_external: "cockpitSetup.transport.mcpEndpoint",
};

type RuntimeStatusMessageKey = "cockpitSetup.status.sidecarStartedForRun";

const RUNTIME_STATUS_MESSAGE_KEYS: Record<
  TaskRuntimeStatus,
  RuntimeStatusMessageKey
> = {
  sidecar_started: "cockpitSetup.status.sidecarStartedForRun",
};

export function taskTransportLabel(
  transport: TaskTransport | undefined,
  t: (key: TransportMessageKey) => string,
): string {
  return transport ? t(TRANSPORT_MESSAGE_KEYS[transport]) : "—";
}

export function taskRuntimeStatusLabel(
  status: TaskRuntimeStatus | undefined,
  t: (key: RuntimeStatusMessageKey) => string,
): string | null {
  return status ? t(RUNTIME_STATUS_MESSAGE_KEYS[status]) : null;
}
