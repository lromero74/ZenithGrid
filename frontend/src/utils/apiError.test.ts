import { describe, it, expect } from 'vitest'
import { getApiErrorMessage, isCanceledRequest } from './apiError'

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

describe('isCanceledRequest', () => {
  it('detects axios cancel/abort codes and CanceledError name', () => {
    expect(isCanceledRequest({ code: 'ERR_CANCELED' })).toBe(true)
    expect(isCanceledRequest({ code: 'ECONNABORTED' })).toBe(true)
    expect(isCanceledRequest({ name: 'CanceledError' })).toBe(true)
  })

  it('returns false for real errors and non-objects', () => {
    expect(isCanceledRequest({ code: 'ERR_BAD_REQUEST' })).toBe(false)
    expect(isCanceledRequest(new Error('boom'))).toBe(false)
    expect(isCanceledRequest(null)).toBe(false)
    expect(isCanceledRequest(undefined)).toBe(false)
    expect(isCanceledRequest('string')).toBe(false)
  })
})
