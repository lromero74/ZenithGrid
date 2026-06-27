/**
 * Session-storage helpers for resuming the last-played game. Extracted from
 * GameHub so the component file only exports a component (Fast Refresh).
 */

const LAST_GAME_KEY = 'zenith-games-last-path'

/** Store the current game path so we can resume it later. */
export function setLastGamePath(path: string): void {
  try { sessionStorage.setItem(LAST_GAME_KEY, path) } catch { /* ignore */ }
}

/** Clear the stored game path (used when explicitly going back to hub). */
export function clearLastGamePath(): void {
  try { sessionStorage.removeItem(LAST_GAME_KEY) } catch { /* ignore */ }
}

/** Read the stored game path, or null if none / storage unavailable. */
export function getLastGamePath(): string | null {
  try { return sessionStorage.getItem(LAST_GAME_KEY) } catch { return null }
}
