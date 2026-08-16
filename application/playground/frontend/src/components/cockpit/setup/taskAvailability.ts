import type { ToneChipTone } from "./ToneChip";

export type TaskAvailabilityStatus = "available" | "unavailable";

type AvailabilityMessageKey =
  | "cockpitSetup.status.available"
  | "cockpitSetup.status.unavailable";

export interface TaskAvailabilityPresentation {
  label: string;
  tone: ToneChipTone;
}

const AVAILABILITY_MESSAGE_KEYS: Record<
  TaskAvailabilityStatus,
  AvailabilityMessageKey
> = {
  available: "cockpitSetup.status.available",
  unavailable: "cockpitSetup.status.unavailable",
};

export function taskAvailabilityPresentation(
  status: TaskAvailabilityStatus | undefined,
  t: (key: AvailabilityMessageKey) => string,
): TaskAvailabilityPresentation | null {
  if (!status) return null;
  return {
    label: t(AVAILABILITY_MESSAGE_KEYS[status]),
    tone: status === "available" ? "secondary" : "danger",
  };
}
