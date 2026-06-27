/**
 * Quarterly scheduling helpers for the donation modal. Extracted from
 * DonationModal so the component file only exports a component (Fast Refresh).
 */

export const DONATION_DISMISSED_QUARTER_KEY = 'donation_modal_dismissed_quarter'

/** Get current quarter string like "2026-Q1" */
export function getCurrentQuarter(): string {
  const now = new Date()
  const q = Math.ceil((now.getMonth() + 1) / 3)
  return `${now.getFullYear()}-Q${q}`
}

/** Check if the donation modal should auto-show this quarter. */
export function shouldShowDonationModal(): boolean {
  const currentQuarter = getCurrentQuarter()
  const dismissedQuarter = localStorage.getItem(DONATION_DISMISSED_QUARTER_KEY)
  return dismissedQuarter !== currentQuarter
}
