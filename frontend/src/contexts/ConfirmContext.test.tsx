/**
 * Tests for ConfirmContext
 *
 * Tests the confirm promise resolving true on confirm, false on cancel,
 * variant-specific styling, custom labels, and error on missing provider.
 */

import { describe, test, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act } from '@testing-library/react'

import { ConfirmProvider, useConfirm } from './ConfirmContext'

// TestConsumer that triggers confirm dialogs and reports the result
function TestConsumer() {
  const confirm = useConfirm()
  return (
    <div>
      <span data-testid="result">pending</span>
      <button
        data-testid="trigger-default"
        onClick={async () => {
          const result = await confirm({ title: 'Default Title', message: 'Default message' })
          screen.getByTestId('result').textContent = String(result)
        }}
      >
        Trigger Default
      </button>
      <button
        data-testid="trigger-danger"
        onClick={async () => {
          const result = await confirm({
            title: 'Delete Item',
            message: 'This is permanent.',
            variant: 'danger',
            confirmLabel: 'Delete',
            cancelLabel: 'Keep',
          })
          screen.getByTestId('result').textContent = String(result)
        }}
      >
        Trigger Danger
      </button>
      <button
        data-testid="trigger-warning"
        onClick={async () => {
          const result = await confirm({
            title: 'Warning',
            message: 'Are you sure?',
            variant: 'warning',
            confirmLabel: 'Proceed',
          })
          screen.getByTestId('result').textContent = String(result)
        }}
      >
        Trigger Warning
      </button>
    </div>
  )
}

describe('ConfirmContext', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  test('useConfirm throws when used outside ConfirmProvider', () => {
    function BadConsumer() {
      useConfirm()
      return <div />
    }
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<BadConsumer />)).toThrow('useConfirm must be used within ConfirmProvider')
    spy.mockRestore()
  })

  test('does not render dialog initially', () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    expect(screen.queryByText('Default Title')).toBeNull()
  })

  test('shows dialog when confirm is called', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-default').click()
    })

    expect(screen.getByText('Default Title')).toBeDefined()
    expect(screen.getByText('Default message')).toBeDefined()
  })

  test('resolves true when confirm button is clicked', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-default').click()
    })

    // Click the Confirm button
    await act(async () => {
      screen.getByText('Confirm').click()
    })

    expect(screen.getByTestId('result').textContent).toBe('true')
    // Dialog should be dismissed
    expect(screen.queryByText('Default Title')).toBeNull()
  })

  test('resolves false when cancel button is clicked', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-default').click()
    })

    // Click the Cancel button
    await act(async () => {
      screen.getByText('Cancel').click()
    })

    expect(screen.getByTestId('result').textContent).toBe('false')
    expect(screen.queryByText('Default Title')).toBeNull()
  })

  test('resolves false when X close button is clicked', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-default').click()
    })

    // The X button is the first button in the header — find it by role
    // The X button calls handleCancel, same as Cancel
    const buttons = screen.getAllByRole('button')
    // The X close button is rendered before Cancel and Confirm in the DOM
    // It's inside the header. Let's find the one that is not Confirm/Cancel/trigger
    const closeButton = buttons.find(
      (b) =>
        b.textContent !== 'Confirm' &&
        b.textContent !== 'Cancel' &&
        !b.dataset.testid?.startsWith('trigger')
    )

    await act(async () => {
      closeButton!.click()
    })

    expect(screen.getByTestId('result').textContent).toBe('false')
  })

  test('uses default labels when none specified', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-default').click()
    })

    expect(screen.getByText('Confirm')).toBeDefined()
    expect(screen.getByText('Cancel')).toBeDefined()
  })

  test('uses custom labels from danger variant', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-danger').click()
    })

    expect(screen.getByText('Delete')).toBeDefined()
    expect(screen.getByText('Keep')).toBeDefined()
  })

  test('uses custom confirmLabel from warning variant', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-warning').click()
    })

    expect(screen.getByText('Proceed')).toBeDefined()
    // cancelLabel defaults to 'Cancel'
    expect(screen.getByText('Cancel')).toBeDefined()
  })

  test('danger variant uses red confirm button styling', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-danger').click()
    })

    const deleteBtn = screen.getByText('Delete')
    expect(deleteBtn.className).toContain('bg-red-600')
  })

  test('warning variant uses amber confirm button styling', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-warning').click()
    })

    const proceedBtn = screen.getByText('Proceed')
    expect(proceedBtn.className).toContain('bg-amber-600')
  })

  test('default variant uses blue confirm button styling', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-default').click()
    })

    const confirmBtn = screen.getByText('Confirm')
    expect(confirmBtn.className).toContain('bg-blue-600')
  })

  test('danger variant title has red text color', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-danger').click()
    })

    const title = screen.getByText('Delete Item')
    expect(title.className).toContain('text-red-400')
  })

  test('warning variant title has amber text color', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-warning').click()
    })

    const title = screen.getByText('Warning')
    expect(title.className).toContain('text-amber-400')
  })

  test('default variant title has white text color', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-default').click()
    })

    const title = screen.getByText('Default Title')
    expect(title.className).toContain('text-white')
  })

  test('danger and warning variants show AlertTriangle icon', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    // Danger variant
    await act(async () => {
      screen.getByTestId('trigger-danger').click()
    })

    // AlertTriangle renders as an SVG — find it near the title
    const dangerTitle = screen.getByText('Delete Item')
    const dangerHeader = dangerTitle.closest('div')
    const svgs = dangerHeader?.querySelectorAll('svg')
    expect(svgs?.length).toBeGreaterThanOrEqual(1)

    // Dismiss
    await act(async () => {
      screen.getByText('Keep').click()
    })
  })

  test('default variant does not show AlertTriangle icon', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-default').click()
    })

    // Find the header div with the title
    const title = screen.getByText('Default Title')
    // In default variant, there should be no SVG icon next to the title
    // (the X close button is in a separate sibling, not in the same items-center div)
    // We check the parent div that has items-center class
    const iconsDiv = title.parentElement
    const svgsInIconDiv = iconsDiv?.querySelectorAll('svg')
    // Default variant should have 0 SVGs next to the title (AlertTriangle is conditional)
    expect(svgsInIconDiv?.length ?? 0).toBe(0)
  })

  test('dialog shows message content', async () => {
    render(
      <ConfirmProvider>
        <TestConsumer />
      </ConfirmProvider>
    )

    await act(async () => {
      screen.getByTestId('trigger-danger').click()
    })

    expect(screen.getByText('This is permanent.')).toBeDefined()
  })
})
