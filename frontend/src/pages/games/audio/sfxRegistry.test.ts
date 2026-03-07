import { describe, it, expect } from 'vitest'
import { SFX_REGISTRY, getGameSFXMap, getRegisteredGameIds, getAllMappedEffects } from './sfxRegistry'
import { SFX_CATALOG } from './sfxCatalog'

// ---------------------------------------------------------------------------
// sfxRegistry tests — validate game→event→effect mappings
// ---------------------------------------------------------------------------

describe('SFX_REGISTRY', () => {
  it('maps all 36 games', () => {
    expect(Object.keys(SFX_REGISTRY).length).toBe(36)
  })

  it('all game IDs use kebab-case', () => {
    for (const gameId of Object.keys(SFX_REGISTRY)) {
      expect(gameId).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/)
    }
  })

  it('all event names use snake_case', () => {
    for (const [gameId, events] of Object.entries(SFX_REGISTRY)) {
      for (const event of Object.keys(events)) {
        expect(event).toMatch(/^[a-z][a-z0-9_]*$/)
      }
    }
  })

  it('all mapped effects exist in SFX_CATALOG', () => {
    for (const [gameId, events] of Object.entries(SFX_REGISTRY)) {
      for (const [event, effectName] of Object.entries(events)) {
        expect(SFX_CATALOG).toHaveProperty(
          effectName,
          expect.any(Function),
        )
      }
    }
  })

  it('every game has at least 2 events mapped', () => {
    for (const [gameId, events] of Object.entries(SFX_REGISTRY)) {
      expect(Object.keys(events).length).toBeGreaterThanOrEqual(2)
    }
  })
})

// ---------------------------------------------------------------------------
// getGameSFXMap
// ---------------------------------------------------------------------------

describe('getGameSFXMap', () => {
  it('returns event map for known game', () => {
    const map = getGameSFXMap('chess')
    expect(map).toBeDefined()
    expect(map!.move).toBe('piece_slide')
    expect(map!.capture).toBe('piece_capture')
  })

  it('returns undefined for unknown game', () => {
    expect(getGameSFXMap('nonexistent-game')).toBeUndefined()
  })

  it('returns correct effects for tic-tac-toe', () => {
    const map = getGameSFXMap('tic-tac-toe')!
    expect(map.place).toBe('piece_place')
    expect(map.win).toBe('victory_fanfare')
    expect(map.draw).toBe('success_small')
  })

  it('returns correct effects for blackjack', () => {
    const map = getGameSFXMap('blackjack')!
    expect(map.deal).toBe('card_deal')
    expect(map.hit).toBe('card_flip')
    expect(map.bust).toBe('error_buzz')
    expect(map.blackjack).toBe('victory_fanfare')
  })

  it('returns correct effects for wordle', () => {
    const map = getGameSFXMap('wordle')!
    expect(map.key).toBe('key_press')
    expect(map.correct).toBe('letter_correct')
    expect(map.wrong).toBe('letter_wrong')
    expect(map.win).toBe('word_reveal')
  })

  it('returns correct effects for dino-runner', () => {
    const map = getGameSFXMap('dino-runner')!
    expect(map.jump).toBe('jump')
    expect(map.die).toBe('collision')
  })

  it('returns correct effects for plinko', () => {
    const map = getGameSFXMap('plinko')!
    expect(map.bounce).toBe('peg_bounce')
    expect(map.land).toBe('ball_land')
  })
})

// ---------------------------------------------------------------------------
// getRegisteredGameIds
// ---------------------------------------------------------------------------

describe('getRegisteredGameIds', () => {
  it('returns all 36 game IDs', () => {
    const ids = getRegisteredGameIds()
    expect(ids.length).toBe(36)
  })

  it('includes key games', () => {
    const ids = getRegisteredGameIds()
    expect(ids).toContain('chess')
    expect(ids).toContain('snake')
    expect(ids).toContain('wordle')
    expect(ids).toContain('dino-runner')
    expect(ids).toContain('blackjack')
  })

  it('has no duplicates', () => {
    const ids = getRegisteredGameIds()
    expect(new Set(ids).size).toBe(ids.length)
  })
})

// ---------------------------------------------------------------------------
// getAllMappedEffects
// ---------------------------------------------------------------------------

describe('getAllMappedEffects', () => {
  it('returns a non-empty set of effect names', () => {
    const effects = getAllMappedEffects()
    expect(effects.size).toBeGreaterThan(0)
  })

  it('all mapped effects are valid catalog entries', () => {
    const effects = getAllMappedEffects()
    for (const name of effects) {
      expect(SFX_CATALOG).toHaveProperty(name)
    }
  })

  it('includes effects from multiple categories', () => {
    const effects = getAllMappedEffects()
    // Should cover card, board, tonal, arcade effects at minimum
    expect(effects.has('card_deal')).toBe(true)
    expect(effects.has('piece_place')).toBe(true)
    expect(effects.has('victory_fanfare')).toBe(true)
    expect(effects.has('laser_fire')).toBe(true)
  })
})
