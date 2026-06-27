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

/**
 * True when an error represents an aborted/canceled request (pair switch,
 * timeout, AbortController) rather than a real failure. Covers axios's
 * `ERR_CANCELED`/`ECONNABORTED` codes and the `CanceledError` name.
 */
export function isCanceledRequest(err: unknown): boolean {
  const e = err as { code?: string; name?: string } | null | undefined
  return e?.code === 'ERR_CANCELED'
    || e?.code === 'ECONNABORTED'
    || e?.name === 'CanceledError'
}
