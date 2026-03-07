import { describe, it, expect } from 'vitest'
import { SFX_CATALOG, SFXRecipe, EFFECT_CATEGORIES } from './sfxCatalog'

// ---------------------------------------------------------------------------
// sfxCatalog tests — validate the effect recipe catalog structure
// ---------------------------------------------------------------------------

describe('SFX_CATALOG', () => {
  it('contains exactly 53 effect recipes', () => {
    expect(Object.keys(SFX_CATALOG).length).toBe(53)
  })

  it('all recipes are functions', () => {
    for (const [name, recipe] of Object.entries(SFX_CATALOG)) {
      expect(typeof recipe).toBe('function')
      // Recipes are: (engine, time, variation) => void
      expect(recipe.length).toBeGreaterThanOrEqual(2) // at least engine + time
    }
  })

  it('all recipe names use snake_case', () => {
    for (const name of Object.keys(SFX_CATALOG)) {
      expect(name).toMatch(/^[a-z][a-z0-9_]*$/)
    }
  })

  // ---- Category: UI Feedback ----

  describe('UI Feedback effects', () => {
    const uiEffects = ['ui_click', 'ui_select', 'ui_error', 'ui_confirm', 'ui_hover', 'ui_toggle']

    it('all UI effects exist', () => {
      for (const name of uiEffects) {
        expect(SFX_CATALOG).toHaveProperty(name)
      }
    })
  })

  // ---- Category: Card & Paper ----

  describe('Card & Paper effects', () => {
    const cardEffects = ['card_flip', 'card_deal', 'card_shuffle', 'card_place', 'card_slide', 'card_fan']

    it('all card effects exist', () => {
      for (const name of cardEffects) {
        expect(SFX_CATALOG).toHaveProperty(name)
      }
    })
  })

  // ---- Category: Board & Piece ----

  describe('Board & Piece effects', () => {
    const boardEffects = [
      'piece_place', 'piece_capture', 'piece_slide', 'piece_drop',
      'tile_click', 'tile_slide', 'tile_merge', 'dice_roll',
    ]

    it('all board effects exist', () => {
      for (const name of boardEffects) {
        expect(SFX_CATALOG).toHaveProperty(name)
      }
    })
  })

  // ---- Category: Tonal Feedback ----

  describe('Tonal Feedback effects', () => {
    const tonalEffects = [
      'success_chime', 'success_small', 'error_buzz', 'warning_beep', 'level_up',
      'victory_fanfare', 'defeat_tone', 'countdown_tick', 'countdown_urgent', 'streak_milestone',
    ]

    it('all tonal effects exist', () => {
      for (const name of tonalEffects) {
        expect(SFX_CATALOG).toHaveProperty(name)
      }
    })
  })

  // ---- Category: Arcade Action ----

  describe('Arcade Action effects', () => {
    const arcadeEffects = [
      'laser_fire', 'explosion', 'explosion_small', 'jump', 'land',
      'collect_coin', 'collect_food', 'collision', 'peg_bounce', 'ball_land',
    ]

    it('all arcade effects exist', () => {
      for (const name of arcadeEffects) {
        expect(SFX_CATALOG).toHaveProperty(name)
      }
    })
  })

  // ---- Category: Word Game ----

  describe('Word Game effects', () => {
    const wordEffects = ['key_press', 'letter_correct', 'letter_wrong', 'word_reveal']

    it('all word effects exist', () => {
      for (const name of wordEffects) {
        expect(SFX_CATALOG).toHaveProperty(name)
      }
    })
  })

  // ---- Category: Ambient/Nature Loops ----

  describe('Ambient/Nature Loop effects', () => {
    const ambientEffects = [
      'ambient_wind', 'ambient_rain', 'ambient_thunder',
      'ambient_crickets', 'ambient_birds', 'ambient_water',
    ]

    it('all ambient effects exist', () => {
      for (const name of ambientEffects) {
        expect(SFX_CATALOG).toHaveProperty(name)
      }
    })
  })

  // ---- Category: Game Over Jingles ----

  describe('Game Over Jingle effects', () => {
    const gameOverEffects = ['gameover_win', 'gameover_lose', 'gameover_draw']

    it('all game over effects exist', () => {
      for (const name of gameOverEffects) {
        expect(SFX_CATALOG).toHaveProperty(name)
      }
    })
  })
})

// ---------------------------------------------------------------------------
// EFFECT_CATEGORIES
// ---------------------------------------------------------------------------

describe('EFFECT_CATEGORIES', () => {
  it('covers all 8 categories', () => {
    expect(Object.keys(EFFECT_CATEGORIES).length).toBe(8)
  })

  it('every effect in catalog belongs to exactly one category', () => {
    const allCategorized = Object.values(EFFECT_CATEGORIES).flat()
    const catalogKeys = Object.keys(SFX_CATALOG)

    // All catalog effects are categorized
    for (const key of catalogKeys) {
      expect(allCategorized).toContain(key)
    }

    // No duplicates across categories
    expect(new Set(allCategorized).size).toBe(allCategorized.length)
  })

  it('all categorized effects exist in catalog', () => {
    const allCategorized = Object.values(EFFECT_CATEGORIES).flat()
    for (const name of allCategorized) {
      expect(SFX_CATALOG).toHaveProperty(name)
    }
  })
})
