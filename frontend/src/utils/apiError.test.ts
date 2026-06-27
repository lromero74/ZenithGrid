import { describe, it, expect } from 'vitest'
import { getApiErrorMessage } from './apiError'

describe('getApiErrorMessage', () => {
  // Happy path: backend-style axios error with a detail string
  it('returns response.data.detail when present', () => {
    const err = { response: { data: { detail: 'Boom from backend' } } }
    expect(getApiErrorMessage(err, 'fallback')).toBe('Boom from backend')
  })

  // Edge case: detail is empty string -> use fallback (matches `|| fallback`)
  it('falls back when detail is an empty string', () => {
    const err = { response: { data: { detail: '' } } }
    expect(getApiErrorMessage(err, 'fallback')).toBe('fallback')
  })

  // Edge case: shape missing pieces along the path
  it('falls back when response/data/detail is missing', () => {
    expect(getApiErrorMessage({ response: {} }, 'fallback')).toBe('fallback')
    expect(getApiErrorMessage({}, 'fallback')).toBe('fallback')
  })

  // Failure cases: non-object errors must not throw
  it('falls back for null, undefined, and primitive errors', () => {
    expect(getApiErrorMessage(null, 'fallback')).toBe('fallback')
    expect(getApiErrorMessage(undefined, 'fallback')).toBe('fallback')
    expect(getApiErrorMessage('a string error', 'fallback')).toBe('fallback')
    expect(getApiErrorMessage(new Error('plain'), 'fallback')).toBe('fallback')
  })

  // Edge case: non-string detail is ignored
  it('falls back when detail is not a string', () => {
    const err = { response: { data: { detail: { nested: true } } } }
    expect(getApiErrorMessage(err, 'fallback')).toBe('fallback')
  })
})
