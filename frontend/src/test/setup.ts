import '@testing-library/jest-dom'

// jsdom 28 ships `window.localStorage` / `window.sessionStorage` as empty
// objects rather than real Storage instances — `getItem` / `setItem` / `clear`
// are undefined. Install an in-memory Web Storage implementation so tests
// that touch localStorage behave the way they would in a real browser.
class MemoryStorage implements Storage {
  private store = new Map<string, string>()
  get length(): number {
    return this.store.size
  }
  clear(): void {
    this.store.clear()
  }
  getItem(key: string): string | null {
    return this.store.has(key) ? (this.store.get(key) as string) : null
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null
  }
  removeItem(key: string): void {
    this.store.delete(key)
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value))
  }
}

const needsPolyfill = (storage: unknown): boolean =>
  !storage || typeof (storage as Storage).getItem !== 'function'

if (needsPolyfill(globalThis.localStorage)) {
  const ls = new MemoryStorage()
  Object.defineProperty(globalThis, 'localStorage', { value: ls, configurable: true, writable: true })
  Object.defineProperty(window, 'localStorage', { value: ls, configurable: true, writable: true })
}

if (needsPolyfill(globalThis.sessionStorage)) {
  const ss = new MemoryStorage()
  Object.defineProperty(globalThis, 'sessionStorage', { value: ss, configurable: true, writable: true })
  Object.defineProperty(window, 'sessionStorage', { value: ss, configurable: true, writable: true })
}
