/**
 * Tests for AccountContext
 *
 * Tests pure helper functions (getChainById, getChainName, SUPPORTED_CHAINS)
 * which don't require React rendering.
 */

import { describe, test, expect } from 'vitest'
import { getChainById, getChainName, SUPPORTED_CHAINS } from './AccountContext'

describe('SUPPORTED_CHAINS', () => {
  test('contains Ethereum', () => {
    const eth = SUPPORTED_CHAINS.find((c) => c.id === 1)
    expect(eth).toBeDefined()
    expect(eth!.name).toBe('Ethereum Mainnet')
    expect(eth!.symbol).toBe('ETH')
  })

  test('contains BSC', () => {
    const bsc = SUPPORTED_CHAINS.find((c) => c.id === 56)
    expect(bsc).toBeDefined()
    expect(bsc!.shortName).toBe('BSC')
  })

  test('contains Polygon', () => {
    const polygon = SUPPORTED_CHAINS.find((c) => c.id === 137)
    expect(polygon).toBeDefined()
    expect(polygon!.symbol).toBe('MATIC')
  })

  test('contains Arbitrum', () => {
    const arb = SUPPORTED_CHAINS.find((c) => c.id === 42161)
    expect(arb).toBeDefined()
    expect(arb!.shortName).toBe('Arbitrum')
  })

  test('all chains have required fields', () => {
    for (const chain of SUPPORTED_CHAINS) {
      expect(chain.id).toBeDefined()
      expect(chain.name).toBeDefined()
      expect(chain.shortName).toBeDefined()
      expect(chain.symbol).toBeDefined()
      expect(chain.rpcUrl).toBeDefined()
      expect(chain.blockExplorer).toBeDefined()
    }
  })
})

describe('getChainById', () => {
  test('returns Ethereum for id 1', () => {
    const chain = getChainById(1)
    expect(chain).toBeDefined()
    expect(chain!.name).toBe('Ethereum Mainnet')
  })

  test('returns undefined for unknown chain', () => {
    expect(getChainById(999999)).toBeUndefined()
  })

  test('returns Arbitrum for id 42161', () => {
    const chain = getChainById(42161)
    expect(chain).toBeDefined()
    expect(chain!.shortName).toBe('Arbitrum')
  })
})

describe('getChainName', () => {
  test('returns shortName for known chain', () => {
    expect(getChainName(1)).toBe('Ethereum')
    expect(getChainName(56)).toBe('BSC')
    expect(getChainName(137)).toBe('Polygon')
  })

  test('returns fallback for unknown chain', () => {
    expect(getChainName(12345)).toBe('Chain 12345')
  })
})
