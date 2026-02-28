/**
 * Tests for voices constants module
 *
 * Verifies containsAdultContent detection, VOICE_CYCLE_IDS composition,
 * CHILD_VOICE_IDS identification, TTS_VOICES data integrity,
 * and TTS_VOICES_BY_ID lookup.
 */

import { describe, test, expect } from 'vitest'
import {
  TTS_VOICES,
  TTS_VOICES_BY_ID,
  VOICE_CYCLE_IDS,
  CHILD_VOICE_IDS,
  ADULT_CONTENT_KEYWORDS,
  containsAdultContent,
} from './voices'

describe('TTS_VOICES data integrity', () => {
  test('has at least 40 voices', () => {
    expect(TTS_VOICES.length).toBeGreaterThanOrEqual(40)
  })

  test('every voice has required fields', () => {
    for (const voice of TTS_VOICES) {
      expect(voice.id).toBeTruthy()
      expect(voice.name).toBeTruthy()
      expect(['Female', 'Male']).toContain(voice.gender)
      expect(voice.locale).toBeTruthy()
    }
  })

  test('all voice IDs are unique', () => {
    const ids = TTS_VOICES.map(v => v.id)
    const uniqueIds = new Set(ids)
    expect(uniqueIds.size).toBe(ids.length)
  })

  test('includes voices from multiple locales', () => {
    const locales = new Set(TTS_VOICES.map(v => v.locale))
    expect(locales.size).toBeGreaterThanOrEqual(10)
    expect(locales.has('US')).toBe(true)
    expect(locales.has('UK')).toBe(true)
    expect(locales.has('AU')).toBe(true)
  })

  test('includes both male and female voices', () => {
    const females = TTS_VOICES.filter(v => v.gender === 'Female')
    const males = TTS_VOICES.filter(v => v.gender === 'Male')
    expect(females.length).toBeGreaterThan(0)
    expect(males.length).toBeGreaterThan(0)
  })
})

describe('TTS_VOICES_BY_ID lookup', () => {
  test('maps every voice by its ID', () => {
    expect(Object.keys(TTS_VOICES_BY_ID).length).toBe(TTS_VOICES.length)
  })

  test('returns correct voice by ID', () => {
    const aria = TTS_VOICES_BY_ID['aria']
    expect(aria).toBeDefined()
    expect(aria.name).toBe('Aria')
    expect(aria.gender).toBe('Female')
    expect(aria.locale).toBe('US')
  })

  test('returns undefined for nonexistent ID', () => {
    expect(TTS_VOICES_BY_ID['nonexistent']).toBeUndefined()
  })
})

describe('VOICE_CYCLE_IDS', () => {
  test('only includes voices from allowed locales', () => {
    const allowedLocales = new Set(['US', 'UK', 'AU', 'CA', 'IE', 'IN', 'NZ', 'ZA'])

    for (const id of VOICE_CYCLE_IDS) {
      const voice = TTS_VOICES_BY_ID[id]
      expect(voice).toBeDefined()
      expect(allowedLocales.has(voice.locale)).toBe(true)
    }
  })

  test('does not include voices from excluded locales', () => {
    const excludedLocales = new Set(['SG', 'HK', 'KE', 'NG', 'PH', 'TZ'])

    for (const id of VOICE_CYCLE_IDS) {
      const voice = TTS_VOICES_BY_ID[id]
      expect(excludedLocales.has(voice.locale)).toBe(false)
    }
  })

  test('has more than 20 voices in the cycle', () => {
    expect(VOICE_CYCLE_IDS.length).toBeGreaterThan(20)
  })

  test('all cycle IDs exist in the main voices list', () => {
    for (const id of VOICE_CYCLE_IDS) {
      expect(TTS_VOICES_BY_ID[id]).toBeDefined()
    }
  })
})

describe('CHILD_VOICE_IDS', () => {
  test('contains exactly the voices marked as child', () => {
    const expected = TTS_VOICES.filter(v => v.child).map(v => v.id)
    expect(CHILD_VOICE_IDS.size).toBe(expected.length)
    for (const id of expected) {
      expect(CHILD_VOICE_IDS.has(id)).toBe(true)
    }
  })

  test('includes known child voices', () => {
    expect(CHILD_VOICE_IDS.has('ana')).toBe(true)
    expect(CHILD_VOICE_IDS.has('maisie')).toBe(true)
  })

  test('does not include adult voices', () => {
    expect(CHILD_VOICE_IDS.has('aria')).toBe(false)
    expect(CHILD_VOICE_IDS.has('guy')).toBe(false)
    expect(CHILD_VOICE_IDS.has('brian')).toBe(false)
  })
})

describe('containsAdultContent', () => {
  test('returns true for text containing sexual keywords', () => {
    expect(containsAdultContent('The article discusses sexual assault cases')).toBe(true)
    expect(containsAdultContent('pornography laws are being reviewed')).toBe(true)
  })

  test('returns true for text containing violence keywords', () => {
    expect(containsAdultContent('Multiple murders reported in the area')).toBe(true)
    expect(containsAdultContent('The terrorist attack shocked the nation')).toBe(true)
  })

  test('returns true for text containing drug keywords', () => {
    expect(containsAdultContent('Fentanyl overdose deaths are rising')).toBe(true)
    expect(containsAdultContent('cocaine trafficking ring busted')).toBe(true)
  })

  test('returns true for text containing alcohol keywords', () => {
    expect(containsAdultContent('New whiskey distillery opens downtown')).toBe(true)
    expect(containsAdultContent('Binge drinking on college campuses')).toBe(true)
  })

  test('returns true for text containing gun keywords', () => {
    expect(containsAdultContent('New firearms legislation proposed')).toBe(true)
    expect(containsAdultContent('Mass shooting at local mall')).toBe(true)
  })

  test('returns true for text containing smoking keywords', () => {
    expect(containsAdultContent('Teen vaping rates have doubled')).toBe(true)
    expect(containsAdultContent('Cigarette taxes are increasing')).toBe(true)
  })

  test('returns false for clean text', () => {
    expect(containsAdultContent('Bitcoin price reached new highs today')).toBe(false)
    expect(containsAdultContent('The weather will be sunny tomorrow')).toBe(false)
    expect(containsAdultContent('New technology startup raises funding')).toBe(false)
  })

  test('returns false for empty string', () => {
    expect(containsAdultContent('')).toBe(false)
  })

  test('matching is case-insensitive', () => {
    expect(containsAdultContent('MURDER case reopened')).toBe(true)
    expect(containsAdultContent('Murder Case Reopened')).toBe(true)
    expect(containsAdultContent('murder case reopened')).toBe(true)
  })

  test('uses word boundaries (no partial matches)', () => {
    // "drug" should match as a whole word but not inside "drugstore" — actually
    // "drug" at the start of "drugstore" IS a word boundary match, so let's
    // test a clear non-boundary case
    expect(containsAdultContent('The play was a smashing hit')).toBe(false)
    expect(containsAdultContent('She sextupled her investment')).toBe(false)
  })

  test('ADULT_CONTENT_KEYWORDS has a reasonable number of entries', () => {
    expect(ADULT_CONTENT_KEYWORDS.length).toBeGreaterThan(100)
  })
})
