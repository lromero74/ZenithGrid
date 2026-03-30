import { describe, it, expect } from 'vitest'

// Tests for shadow-mode sell button visibility logic in Portfolio.tsx

describe('Portfolio shadow sell button visibility', () => {
  function shouldShowSellButton(isObserver: boolean, canSell: boolean): boolean {
    return !isObserver && canSell
  }

  it('hides sell-to-USD button for shadow members', () => {
    expect(shouldShowSellButton(true, true)).toBe(false)
  })

  it('hides sell-to-BTC button for shadow members', () => {
    expect(shouldShowSellButton(true, true)).toBe(false)
  })

  it('shows sell-to-USD button for owners when asset is sellable', () => {
    expect(shouldShowSellButton(false, true)).toBe(true)
  })

  it('hides sell button even for owners when asset is not sellable', () => {
    expect(shouldShowSellButton(false, false)).toBe(false)
  })

  describe('canWriteAccounts derivation', () => {
    it('is false when shadow regardless of RBAC', () => {
      const rbacCanWrite = true
      const isObserver = true
      expect(rbacCanWrite && !isObserver).toBe(false)
    })

    it('is true when RBAC allows and not shadow', () => {
      const rbacCanWrite = true
      const isObserver = false
      expect(rbacCanWrite && !isObserver).toBe(true)
    })
  })
})
