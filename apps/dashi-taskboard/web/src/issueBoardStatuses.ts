import type { TaskStatus } from "./types";

export const MAIN_STATUSES = [
  "todo",
  "backlog",
  "in_progress",
  "blocked",
  "in_review",
  "done",
] as const satisfies readonly TaskStatus[];

export const SECONDARY_STATUSES = [
  "canceled",
] as const satisfies readonly TaskStatus[];

export type MainTaskStatus = (typeof MAIN_STATUSES)[number];
export type SecondaryTaskStatus = (typeof SECONDARY_STATUSES)[number];
export type OtherTaskTab = TaskStatus | "archived";
