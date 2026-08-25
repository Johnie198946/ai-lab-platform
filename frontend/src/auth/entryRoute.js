export const SHOWROOM_CONTROLLER_PATH = "/architect";

const SHOWROOM_IDENTITIES = new Set([
  "showroom",
  "showroom_controller",
  "showroom_demo",
]);

const normalizeIdentity = (value) => String(value ?? "").trim().toLowerCase();

export function isShowroomAccount(user) {
  if (SHOWROOM_IDENTITIES.has(normalizeIdentity(user?.username))) {
    return true;
  }

  const roles = Array.isArray(user?.roles) ? user.roles : [];
  return roles.some((role) =>
    SHOWROOM_IDENTITIES.has(
      normalizeIdentity(typeof role === "string" ? role : role?.name || role?.code || role?.key),
    ),
  );
}
