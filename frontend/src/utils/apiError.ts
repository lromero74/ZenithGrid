import { AxiosError } from 'axios'

/**
 * Safely extract a human-readable message from an unknown error thrown by an
 * API call. Mirrors the long-standing `err.response?.data?.detail || fallback`
 * pattern (the backend returns errors as `{ detail: string }`) but without an
 * `any` cast: narrows `unknown` to an AxiosError before reading `.detail`, and
 * returns the supplied fallback for anything else.
 */
export function getApiErrorMessage(err: unknown, fallback: string): string {
  const detail = (err as AxiosError<{ detail?: string }>)?.response?.data?.detail
  if (typeof detail === 'string' && detail) return detail
  return fallback
}
