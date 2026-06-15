/**
 * Guard for the v3.0.0 white-screen regression.
 *
 * The bridge was mounted in App.tsx OUTSIDE NotificationProvider, so its
 * useNotifications() threw and crashed the whole app to a blank screen. Isolated
 * provider tests didn't catch it because they mount the provider directly — the
 * mistake was the bridge's PLACEMENT in App.tsx.
 *
 * The durable guard: the bridge must NEVER throw on render, no matter where it's
 * mounted. It now uses non-throwing context accessors and degrades silently.
 * This test renders it with NO providers (the exact broken condition) and proves
 * it doesn't throw — it would have failed on the old throwing code.
 */
import { describe, test, expect } from 'vitest'
import { render } from '@testing-library/react'

import { PaperNotificationBridge } from '../App'

describe('PaperNotificationBridge', () => {
  test('does not throw when rendered with NO providers (no white-screen)', () => {
    // The pre-fix bug: this threw "useNotifications must be used within
    // NotificationProvider" and blanked the app. With non-throwing accessors it
    // degrades silently instead.
    expect(() => render(<PaperNotificationBridge />)).not.toThrow()
  })

  test('renders nothing (it is a side-effect-only bridge)', () => {
    const { container } = render(<PaperNotificationBridge />)
    expect(container.firstChild).toBeNull()
  })
})
