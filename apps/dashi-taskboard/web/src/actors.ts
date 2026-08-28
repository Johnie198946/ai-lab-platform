import type { ActorIdentity, AssigneeTarget } from "./types";

export const CODEX_AGENT_ACTOR: ActorIdentity = {
  type: "agent",
  id: "codex-agent",
  name: "AI Lab AI 员工",
  avatarUrl: null,
};

export function actorKey(actor: ActorIdentity): string {
  return `${actor.type}:${actor.id}`;
}

export function actorForAssigneeTarget(
  target: AssigneeTarget,
  currentUser: ActorIdentity,
): ActorIdentity {
  if (target === "current-user") return currentUser;
  if (target === "codex-agent") return CODEX_AGENT_ACTOR;
  return {
    type: "agent",
    id: target.slice("ai-employee:".length),
    name: "AI Lab AI 员工",
    avatarUrl: null,
  };
}

export function assigneeTargetForActor(
  actor: ActorIdentity,
  currentUser: ActorIdentity,
): AssigneeTarget | undefined {
  if (actor.type === "agent" && /^[a-f0-9]{32}$/.test(actor.id)) {
    return `ai-employee:${actor.id}`;
  }
  if (actor.type === "agent") return "codex-agent";
  return actor.id === currentUser.id ? "current-user" : undefined;
}
