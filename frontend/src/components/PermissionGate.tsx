/**
 * PermissionGate Component
 *
 * Conditionally renders children based on RBAC permissions.
 * Superusers bypass all permission checks.
 */

import { ReactNode } from 'react'
import { usePermission } from '../hooks/usePermission'

interface PermissionGateProps {
  resource: string
  action: string
  fallback?: ReactNode
  children: ReactNode
}

export function PermissionGate({ resource, action, fallback = null, children }: PermissionGateProps) {
  const hasPermission = usePermission(resource, action)
  return hasPermission ? <>{children}</> : <>{fallback}</>
}
