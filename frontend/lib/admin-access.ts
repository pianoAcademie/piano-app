import type { ProfessorPermissionOut, UserOut } from "./types";
import type { UiLanguage } from "./ui-i18n";

export type AdminPermissionKey = keyof ProfessorPermissionOut;

export const MANAGER_ADMIN_PERMISSION_KEYS: AdminPermissionKey[] = [
  "can_view_planning",
  "can_edit_planning",
  "can_view_planning_simulation",
  "can_view_clients",
  "can_access_collaborators",
  "can_view_intakes",
  "can_view_quotes",
  "can_manage_events",
];

export function hasAdminPermission(user: UserOut, key: AdminPermissionKey): boolean {
  if (key === "can_view_planning" && Boolean(user.admin_permissions?.can_edit_planning)) {
    return true;
  }
  return user.role === "admin" || Boolean(user.admin_permissions?.[key]);
}

export function hasAnyAdminAccess(user: UserOut): boolean {
  return user.role === "admin" || MANAGER_ADMIN_PERMISSION_KEYS.some((key) => hasAdminPermission(user, key));
}

export function adminRoleLabel(user: UserOut, language: UiLanguage): string {
  if (user.role === "admin") {
    return language === "en" ? "Administrator" : "Administrateur";
  }
  if (hasAnyAdminAccess(user)) {
    return language === "en" ? "Manager" : "Gestionnaire";
  }
  return language === "en" ? "Teacher" : "Professeur";
}
