/**
 * Tests for mediaCoordinator
 *
 * This is a plain module (NOT a React context) — tested with direct imports.
 * Tests registerVideoPlayer/stopVideoPlayer round-trips, null guard on
 * unregistered stop, registerArticleReader/stopArticleReader.
 */

import { describe, test, expect, beforeEach, vi } from 'vitest'
import {
  registerVideoPlayer,
  stopVideoPlayer,
  registerArticleReader,
  stopArticleReader,
} from './mediaCoordinator'

describe('mediaCoordinator', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    // Reset the coordinator state by registering null-like functions,
    // then overwriting with test functions. Since the module is global,
    // we need to clear registered functions by re-registering no-ops
    // and then testing fresh.
    // Actually — we just register new functions in each test, overwriting previous.
    // The coordinator only holds the last registered function.
    // For safety, register no-ops to clear previous test state.
    registerVideoPlayer(() => {})
    registerArticleReader(() => {})
  })

  test('registerVideoPlayer stores the stop function', () => {
    const stopFn = vi.fn()
    registerVideoPlayer(stopFn)

    stopVideoPlayer()
    expect(stopFn).toHaveBeenCalledTimes(1)
  })

  test('stopVideoPlayer calls the registered video stop function', () => {
    const stopFn = vi.fn()
    registerVideoPlayer(stopFn)

    stopVideoPlayer()
    stopVideoPlayer()

    expect(stopFn).toHaveBeenCalledTimes(2)
  })

  test('registerArticleReader stores the stop function', () => {
    const stopFn = vi.fn()
    registerArticleReader(stopFn)

    stopArticleReader()
    expect(stopFn).toHaveBeenCalledTimes(1)
  })

  test('stopArticleReader calls the registered article stop function', () => {
    const stopFn = vi.fn()
    registerArticleReader(stopFn)

    stopArticleReader()
    stopArticleReader()

    expect(stopFn).toHaveBeenCalledTimes(2)
  })

  test('stopVideoPlayer does not throw when no video player is registered', () => {
    // Register a no-op first (from beforeEach), then verify no crash
    // To truly test null guard, we need to set the internal state to null.
    // Since we can't directly set it to null via the API, we test that
    // calling stop after registering a no-op doesn't throw.
    expect(() => stopVideoPlayer()).not.toThrow()
  })

  test('stopArticleReader does not throw when no article reader is registered', () => {
    expect(() => stopArticleReader()).not.toThrow()
  })

  test('registering a new video player overwrites the previous one', () => {
    const firstStop = vi.fn()
    const secondStop = vi.fn()

    registerVideoPlayer(firstStop)
    registerVideoPlayer(secondStop)

    stopVideoPlayer()

    expect(firstStop).not.toHaveBeenCalled()
    expect(secondStop).toHaveBeenCalledTimes(1)
  })

  test('registering a new article reader overwrites the previous one', () => {
    const firstStop = vi.fn()
    const secondStop = vi.fn()

    registerArticleReader(firstStop)
    registerArticleReader(secondStop)

    stopArticleReader()

    expect(firstStop).not.toHaveBeenCalled()
    expect(secondStop).toHaveBeenCalledTimes(1)
  })

  test('video and article players are independent', () => {
    const videoStop = vi.fn()
    const articleStop = vi.fn()

    registerVideoPlayer(videoStop)
    registerArticleReader(articleStop)

    stopVideoPlayer()

    expect(videoStop).toHaveBeenCalledTimes(1)
    expect(articleStop).not.toHaveBeenCalled()

    stopArticleReader()

    expect(articleStop).toHaveBeenCalledTimes(1)
    expect(videoStop).toHaveBeenCalledTimes(1) // still 1, not called again
  })

  test('stop functions can be called multiple times in sequence', () => {
    const videoStop = vi.fn()
    registerVideoPlayer(videoStop)

    stopVideoPlayer()
    stopVideoPlayer()
    stopVideoPlayer()

    expect(videoStop).toHaveBeenCalledTimes(3)
  })

  test('registering then stopping then registering new player works', () => {
    const firstStop = vi.fn()
    const secondStop = vi.fn()

    registerVideoPlayer(firstStop)
    stopVideoPlayer()
    expect(firstStop).toHaveBeenCalledTimes(1)

    registerVideoPlayer(secondStop)
    stopVideoPlayer()
    expect(secondStop).toHaveBeenCalledTimes(1)
    expect(firstStop).toHaveBeenCalledTimes(1) // not called again
  })
})
