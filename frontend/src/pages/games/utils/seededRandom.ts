/**
 * Seeded PRNG — mulberry32 algorithm.
 *
 * Returns a factory that creates a deterministic Math.random() replacement.
 * Two players with the same seed will get the same sequence of numbers.
 */

export function createSeededRandom(seed: number): () => number {
  let s = seed | 0
  return () => {
    s = (s + 0x6D2B79F5) | 0
    let t = Math.imul(s ^ (s >>> 15), 1 | s)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
