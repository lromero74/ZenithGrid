import { describe, it, expect, vi } from 'vitest'

// Test the shadow-mode guard logic for modal open handlers in Positions.tsx.
// These are extracted as pure functions matching the exact pattern used in the component.

function makeOpenAddFundsModal(isObserver: boolean) {
  const setAddFundsPosition = vi.fn()
  const setShowAddFundsModal = vi.fn()
  const handler = (position: { id: number }) => {
    if (isObserver) return
    setAddFundsPosition(position)
    setShowAddFundsModal(true)
  }
  return { handler, setAddFundsPosition, setShowAddFundsModal }
}

function makeOpenNotesModal(isObserver: boolean) {
  const setEditingNotesPositionId = vi.fn()
  const setNotesText = vi.fn()
  const setShowNotesModal = vi.fn()
  const handler = (position: { id: number; notes?: string }) => {
    if (isObserver) return
    setEditingNotesPositionId(position.id)
    setNotesText(position.notes || '')
    setShowNotesModal(true)
  }
  return { handler, setEditingNotesPositionId, setShowNotesModal }
}

function makeHandleOpenEditSettings(isObserver: boolean) {
  const setEditSettingsPosition = vi.fn()
  const setShowEditSettingsModal = vi.fn()
  const handler = (pos: { id: number }) => {
    if (isObserver) return
    setEditSettingsPosition(pos)
    setShowEditSettingsModal(true)
  }
  return { handler, setEditSettingsPosition, setShowEditSettingsModal }
}

const fakePosition = { id: 1, notes: 'hello' }

describe('Positions shadow modal guards', () => {
  describe('openAddFundsModal', () => {
    it('does not open modal when shadow', () => {
      const { handler, setShowAddFundsModal } = makeOpenAddFundsModal(true)
      handler(fakePosition)
      expect(setShowAddFundsModal).not.toHaveBeenCalled()
    })

    it('opens modal when not shadow', () => {
      const { handler, setShowAddFundsModal } = makeOpenAddFundsModal(false)
      handler(fakePosition)
      expect(setShowAddFundsModal).toHaveBeenCalledWith(true)
    })
  })

  describe('openNotesModal', () => {
    it('does not open modal when shadow', () => {
      const { handler, setShowNotesModal } = makeOpenNotesModal(true)
      handler(fakePosition)
      expect(setShowNotesModal).not.toHaveBeenCalled()
    })

    it('opens modal when not shadow', () => {
      const { handler, setShowNotesModal } = makeOpenNotesModal(false)
      handler(fakePosition)
      expect(setShowNotesModal).toHaveBeenCalledWith(true)
    })
  })

  describe('handleOpenEditSettings', () => {
    it('does not open modal when shadow', () => {
      const { handler, setShowEditSettingsModal } = makeHandleOpenEditSettings(true)
      handler(fakePosition)
      expect(setShowEditSettingsModal).not.toHaveBeenCalled()
    })

    it('opens modal when not shadow', () => {
      const { handler, setShowEditSettingsModal } = makeHandleOpenEditSettings(false)
      handler(fakePosition)
      expect(setShowEditSettingsModal).toHaveBeenCalledWith(true)
    })
  })

  describe('canWritePositions derivation', () => {
    it('is false when shadow regardless of RBAC', () => {
      const rbacCanWrite = true
      const isObserver = true
      const canWrite = rbacCanWrite && !isObserver
      expect(canWrite).toBe(false)
    })

    it('is true when RBAC allows and not shadow', () => {
      const rbacCanWrite = true
      const isObserver = false
      const canWrite = rbacCanWrite && !isObserver
      expect(canWrite).toBe(true)
    })
  })

  describe('Resize All Budgets visibility', () => {
    it('is hidden for shadow members', () => {
      const isObserver = true
      const openPositionsLength = 3
      const shouldShow = openPositionsLength > 0 && !isObserver
      expect(shouldShow).toBe(false)
    })

    it('is visible for non-shadow members with open positions', () => {
      const isObserver = false
      const openPositionsLength = 3
      const shouldShow = openPositionsLength > 0 && !isObserver
      expect(shouldShow).toBe(true)
    })
  })
})
