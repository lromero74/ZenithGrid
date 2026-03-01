/**
 * RBAC permission hooks.
 *
 * Check user permissions resolved from the Groups → Roles → Permissions chain.
 * Superusers bypass all checks.
 */

import { useAuth } from '../contexts/AuthContext'

/**
 * Check if the current user has a specific resource:action permission.
 * Superusers always return true.
 */
export function usePermission(resource: string, action: string): boolean {
  const { user } = useAuth()
  if (!user) return false
  if (user.is_superuser) return true
  return user.permissions?.includes(`${resource}:${action}`) ?? false
}

/**
 * Check if the current user has a full permission string (e.g. "admin:users").
 * Superusers always return true.
 */
export function useHasPermission(permission: string): boolean {
  const { user } = useAuth()
  if (!user) return false
  if (user.is_superuser) return true
  return user.permissions?.includes(permission) ?? false
}

/**
 * Check if the current user has any admin-level permission.
 * Returns true for superusers or users with any "admin:*" permission.
 */
export function useIsAdmin(): boolean {
  const { user } = useAuth()
  if (!user) return false
  if (user.is_superuser) return true
  return user.permissions?.some(p => p.startsWith('admin:')) ?? false
}
