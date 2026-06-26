/**
 * Workspace role catalog for the dashboard UI.
 *
 * Mirrors the backend source of truth in `backend/app/core/roles.py`
 * (`AssignableRole`). `owner` is intentionally excluded — ownership is
 * established at workspace creation and transferred through dedicated flows, so
 * it is never offered in role pickers.
 *
 * Keep this list in sync with the backend `AssignableRole` literal; the
 * generated OpenAPI types (`InvitationCreate.role`, `UpdateMemberRoleRequest`)
 * are the contract these dropdowns must satisfy.
 */

export const ASSIGNABLE_ROLES = [
  "admin",
  "manager",
  "dispatcher",
  "sales_rep",
  "technician",
  "member",
] as const;

export type AssignableRole = (typeof ASSIGNABLE_ROLES)[number];

/** Human-readable label for any workspace role, including `owner`. */
export const ROLE_LABELS: Record<string, string> = {
  owner: "Owner",
  admin: "Admin",
  manager: "Manager",
  dispatcher: "Dispatcher",
  sales_rep: "Sales Rep",
  technician: "Technician",
  member: "Member",
};

/** Short description shown beneath each role option in pickers. */
export const ROLE_DESCRIPTIONS: Record<AssignableRole, string> = {
  admin: "Full access including team and billing management",
  manager: "Manage maintenance plans, schedules, and crews",
  dispatcher: "Assign jobs and run the dispatch board",
  sales_rep: "Sell and track personal KPIs in the sales portal",
  technician: "Field tech — view and update assigned jobs",
  member: "View and manage contacts and campaigns",
};

/** Display label for a role string, falling back to the raw value. */
export function roleLabel(role: string): string {
  return ROLE_LABELS[role] ?? role;
}
