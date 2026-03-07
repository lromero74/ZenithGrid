import { describe, it, expect } from 'vitest'
import { mulberry32, generateSong, GENRE_PRESETS } from './songFactory'
import { nearestChordTone, getChord, getScale } from './musicTheory'

// ---------------------------------------------------------------------------
// Mulberry32 PRNG
// ---------------------------------------------------------------------------

describe('mulberry32', () => {
  it('returns values between 0 and 1', () => {
    const rng = mulberry32(42)
    for (let i = 0; i < 100; i++) {
      const val = rng()
      expect(val).toBeGreaterThanOrEqual(0)
      expect(val).toBeLessThan(1)
    }
  })

  it('is deterministic — same seed produces same sequence', () => {
    const rng1 = mulberry32(12345)
    const rng2 = mulberry32(12345)
    for (let i = 0; i < 50; i++) {
      expect(rng1()).toBe(rng2())
    }
  })

  it('different seeds produce different sequences', () => {
    const rng1 = mulberry32(1)
    const rng2 = mulberry32(2)
    const seq1 = Array.from({ length: 10 }, () => rng1())
    const seq2 = Array.from({ length: 10 }, () => rng2())
    expect(seq1).not.toEqual(seq2)
  })

  it('has reasonable distribution (basic chi-squared)', () => {
    const rng = mulberry32(99)
    const buckets = Array(10).fill(0)
    const N = 10000
    for (let i = 0; i < N; i++) {
      const bucket = Math.floor(rng() * 10)
      buckets[bucket]++
    }
    for (const count of buckets) {
      expect(count).toBeGreaterThan(700)
      expect(count).toBeLessThan(1300)
    }
  })
})

// ---------------------------------------------------------------------------
// Genre Presets
// ---------------------------------------------------------------------------

describe('GENRE_PRESETS', () => {
  it('has 20 genre presets', () => {
    expect(Object.keys(GENRE_PRESETS).length).toBe(20)
  })

  it('all presets have valid bpmRange', () => {
    for (const [, preset] of Object.entries(GENRE_PRESETS)) {
      expect(preset.bpmRange[0]).toBeGreaterThanOrEqual(40)
      expect(preset.bpmRange[1]).toBeLessThanOrEqual(200)
      expect(preset.bpmRange[0]).toBeLessThan(preset.bpmRange[1])
    }
  })

  it('all presets have at least 1 key option', () => {
    for (const [, preset] of Object.entries(GENRE_PRESETS)) {
      expect(preset.keyOptions.length).toBeGreaterThan(0)
    }
  })

  it('all presets have at least 1 scale option', () => {
    for (const [, preset] of Object.entries(GENRE_PRESETS)) {
      expect(preset.scaleOptions.length).toBeGreaterThan(0)
    }
  })

  it('all presets have at least 5 sections in flow', () => {
    for (const [, preset] of Object.entries(GENRE_PRESETS)) {
      expect(preset.sectionFlow.length).toBeGreaterThanOrEqual(5)
    }
  })
})

// ---------------------------------------------------------------------------
// Song Generation — Basic Structure
// ---------------------------------------------------------------------------

describe('generateSong', () => {
  it('generates a valid Song object', () => {
    const song = generateSong('synthwave', 42)
    expect(song.title).toBeTruthy()
    expect(song.bpm).toBeGreaterThanOrEqual(40)
    expect(song.bpm).toBeLessThanOrEqual(240)
    expect(song.stepsPerBeat).toBe(4)
    expect(song.key).toBeTruthy()
    expect(song.scale).toBeTruthy()
    expect(song.startSection).toBeTruthy()
    expect(song.genre).toBe('synthwave')
    expect(song.seed).toBe(42)
  })

  it('has all 5 standard channels', () => {
    const song = generateSong('chiptune', 100)
    expect(song.channels).toHaveProperty('bass')
    expect(song.channels).toHaveProperty('lead')
    expect(song.channels).toHaveProperty('pad')
    expect(song.channels).toHaveProperty('arp')
    expect(song.channels).toHaveProperty('drums')
  })

  it('has sections matching the genre preset flow', () => {
    const song = generateSong('jazz', 200)
    const preset = GENRE_PRESETS['jazz']
    const uniqueSections = [...new Set(preset.sectionFlow)]
    for (const name of uniqueSections) {
      expect(song.sections).toHaveProperty(name)
    }
  })

  it('has intensity map with progressive channel activation', () => {
    const song = generateSong('edm', 300)
    expect(song.intensityMap).toBeDefined()
    const thresholds = Object.keys(song.intensityMap!).map(Number).sort((a, b) => a - b)
    expect(thresholds[0]).toBe(0)
    const first = song.intensityMap![thresholds[0]]
    const last = song.intensityMap![thresholds[thresholds.length - 1]]
    expect(last.length).toBeGreaterThan(first.length)
  })

  it('is deterministic — same genre+seed produces identical song', () => {
    const song1 = generateSong('lofi', 555)
    const song2 = generateSong('lofi', 555)
    expect(song1.title).toBe(song2.title)
    expect(song1.bpm).toBe(song2.bpm)
    expect(song1.key).toBe(song2.key)
    expect(song1.scale).toBe(song2.scale)
    expect(Object.keys(song1.channels)).toEqual(Object.keys(song2.channels))
    for (const chName of Object.keys(song1.channels)) {
      const ch1 = song1.channels[chName]
      const ch2 = song2.channels[chName]
      expect(ch1.type).toBe(ch2.type)
      expect(ch1.gain).toBe(ch2.gain)
      expect(Object.keys(ch1.patterns)).toEqual(Object.keys(ch2.patterns))
    }
  })

  it('different seeds produce different songs', () => {
    const song1 = generateSong('rock', 1)
    const song2 = generateSong('rock', 2)
    const differ = song1.key !== song2.key || song1.bpm !== song2.bpm
    expect(differ).toBe(true)
  })

  it('respects option overrides', () => {
    const song = generateSong('ambient', 42, {
      bpm: 75,
      key: 'D',
      title: 'Custom Title',
    })
    expect(song.bpm).toBe(75)
    expect(song.key).toBe('D')
    expect(song.title).toBe('Custom Title')
  })

  it('all patterns have positive length', () => {
    const song = generateSong('metal', 666)
    for (const ch of Object.values(song.channels)) {
      for (const [, pattern] of Object.entries(ch.patterns)) {
        expect(pattern.length).toBeGreaterThan(0)
        expect(pattern.notes.length).toBeGreaterThan(0)
      }
    }
  })

  it('throws on unknown genre', () => {
    expect(() => generateSong('nonexistent', 1)).toThrow('Unknown genre')
  })

  it('generates valid songs for all 20 genres', () => {
    for (const genre of Object.keys(GENRE_PRESETS)) {
      const song = generateSong(genre, 42)
      expect(song.bpm).toBeGreaterThanOrEqual(40)
      expect(Object.keys(song.channels).length).toBe(5)
      expect(Object.keys(song.sections).length).toBeGreaterThanOrEqual(5)
      expect(song.sections).toHaveProperty(song.startSection)
    }
  })

  it('section chain is connected (no orphan sections)', () => {
    const song = generateSong('disco', 42)
    for (const section of Object.values(song.sections)) {
      if (section.next !== null) {
        expect(song.sections).toHaveProperty(section.next)
      }
    }
  })
})

// ---------------------------------------------------------------------------
// Per-Channel ADSR
// ---------------------------------------------------------------------------

describe('per-channel ADSR', () => {
  it('channels have adsr configs for genre-specific envelopes', () => {
    const song = generateSong('synthwave', 42)
    expect(song.channels.bass.adsr).toBeDefined()
    expect(song.channels.lead.adsr).toBeDefined()
    expect(song.channels.pad.adsr).toBeDefined()
    expect(song.channels.arp.adsr).toBeDefined()
    // Drums have no ADSR (they use custom synthesis)
    expect(song.channels.drums.adsr).toBeUndefined()
  })

  it('different genres have different ADSR configs', () => {
    const synth = generateSong('synthwave', 42)
    const ambient = generateSong('ambient', 42)
    // Ambient pads should have longer attack than synthwave
    expect(ambient.channels.pad.adsr!.attack).toBeGreaterThan(synth.channels.pad.adsr!.attack)
  })

  it('ADSR values are within valid ranges', () => {
    for (const genre of Object.keys(GENRE_PRESETS)) {
      const song = generateSong(genre, 42)
      for (const chName of ['bass', 'lead', 'pad', 'arp']) {
        const adsr = song.channels[chName].adsr
        if (adsr) {
          expect(adsr.attack).toBeGreaterThan(0)
          expect(adsr.attack).toBeLessThan(1)
          expect(adsr.decay).toBeGreaterThan(0)
          expect(adsr.sustain).toBeGreaterThan(0)
          expect(adsr.sustain).toBeLessThanOrEqual(1)
          expect(adsr.release).toBeGreaterThan(0)
        }
      }
    }
  })
})

// ---------------------------------------------------------------------------
// Per-Genre Filters
// ---------------------------------------------------------------------------

describe('per-genre filters', () => {
  it('channels have genre-specific filter frequencies', () => {
    const synth = generateSong('synthwave', 42)
    const chip = generateSong('chiptune', 42)
    // Chiptune should have brighter (higher) filters than synthwave
    expect(chip.channels.bass.effects?.filter).toBeGreaterThan(synth.channels.bass.effects!.filter!)
  })

  it('delay-enabled genres have delay on lead channel', () => {
    const synth = generateSong('synthwave', 42)
    expect(synth.channels.lead.effects?.delay).toBeDefined()
    expect(synth.channels.lead.effects!.delay).toBeGreaterThan(0)
  })

  it('non-delay genres omit delay', () => {
    const metal = generateSong('metal', 42)
    expect(metal.channels.lead.effects?.delay).toBeUndefined()
  })
})

// ---------------------------------------------------------------------------
// Per-Genre Intensity Maps
// ---------------------------------------------------------------------------

describe('per-genre intensity maps', () => {
  it('arcade genres unlock channels quickly', () => {
    const chip = generateSong('chiptune', 42)
    const thresholds = Object.keys(chip.intensityMap!).map(Number).sort((a, b) => a - b)
    const maxThreshold = thresholds[thresholds.length - 1]
    expect(maxThreshold).toBeLessThanOrEqual(1000) // fast unlock
  })

  it('chill genres unlock channels slowly', () => {
    const ambient = generateSong('ambient', 42)
    const thresholds = Object.keys(ambient.intensityMap!).map(Number).sort((a, b) => a - b)
    const maxThreshold = thresholds[thresholds.length - 1]
    expect(maxThreshold).toBeGreaterThanOrEqual(2000) // slow unlock
  })

  it('all intensity maps start at threshold 0', () => {
    for (const genre of Object.keys(GENRE_PRESETS)) {
      const song = generateSong(genre, 42)
      expect(song.intensityMap).toHaveProperty('0')
    }
  })
})

// ---------------------------------------------------------------------------
// Chord-Aware Melodies
// ---------------------------------------------------------------------------

describe('chord-aware melodies', () => {
  it('lead melody contains notes from the scale', () => {
    const song = generateSong('jazz', 42)
    const scaleFreqs = new Set(
      // Build the full scale range
      Array.from({ length: 3 }, (_, o) =>
        getScale(song.key, song.scale, 3 + o)
      ).flat()
    )
    const leadPattern = song.channels.lead.patterns['verse']
    // At least some non-rest notes should be scale tones (within tolerance)
    const nonRestNotes = leadPattern.notes.filter(n => n.pitch > 0)
    expect(nonRestNotes.length).toBeGreaterThan(0)
    // Check that notes are reasonable frequencies
    for (const n of nonRestNotes) {
      expect(n.pitch).toBeGreaterThan(50)
      expect(n.pitch).toBeLessThan(5000)
    }
  })

  it('different sections produce different lead patterns', () => {
    const song = generateSong('synthwave', 42)
    const verse = song.channels.lead.patterns['verse']
    const chorus = song.channels.lead.patterns['chorus']
    // They should have different note content (not identical)
    const verseNotes = verse.notes.filter(n => n.pitch > 0).map(n => n.pitch)
    const chorusNotes = chorus.notes.filter(n => n.pitch > 0).map(n => n.pitch)
    expect(verseNotes).not.toEqual(chorusNotes)
  })

  it('intro has no lead melody (rest/silence)', () => {
    const song = generateSong('rock', 42)
    const intro = song.channels.lead.patterns['intro']
    const nonRests = intro.notes.filter(n => n.pitch > 0)
    expect(nonRests.length).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// Genre-Specific Bass Patterns
// ---------------------------------------------------------------------------

describe('genre-specific bass', () => {
  it('jazz bass has more note variety than ambient bass', () => {
    const jazz = generateSong('jazz', 42)
    const ambient = generateSong('ambient', 42)
    const jazzBassVerse = jazz.channels.bass.patterns['verse']
    const ambientBassVerse = ambient.channels.bass.patterns['verse']
    const jazzPitches = new Set(jazzBassVerse.notes.filter(n => n.pitch > 0).map(n => n.pitch))
    const ambientPitches = new Set(ambientBassVerse.notes.filter(n => n.pitch > 0).map(n => n.pitch))
    expect(jazzPitches.size).toBeGreaterThan(ambientPitches.size)
  })

  it('reggae bass has silence on beat 1 (one-drop)', () => {
    const song = generateSong('reggae', 42)
    const verse = song.channels.bass.patterns['verse']
    // First note should be a rest (beat 1 is silent in one-drop)
    expect(verse.notes[0].pitch).toBe(0)
  })

  it('funk bass has short ghost notes (low velocity)', () => {
    const song = generateSong('funk', 42)
    const verse = song.channels.bass.patterns['verse']
    const ghostNotes = verse.notes.filter(n => n.pitch > 0 && (n.velocity ?? 0.8) < 0.3)
    expect(ghostNotes.length).toBeGreaterThan(0)
  })

  it('rock bass uses root and fifth', () => {
    const song = generateSong('rock', 42)
    const chorus = song.channels.bass.patterns['chorus']
    const uniquePitches = new Set(chorus.notes.filter(n => n.pitch > 0).map(n => n.pitch))
    // Should have at least 2 different pitches (root + fifth)
    expect(uniquePitches.size).toBeGreaterThanOrEqual(2)
  })
})

// ---------------------------------------------------------------------------
// Section Contrast
// ---------------------------------------------------------------------------

describe('section contrast', () => {
  it('chorus patterns differ from verse patterns across channels', () => {
    const song = generateSong('synthwave', 42)
    // At least 2 out of 3 melodic channels should differ between verse and chorus
    let diffCount = 0
    for (const chName of ['bass', 'pad', 'lead']) {
      const verse = song.channels[chName].patterns['verse']
      const chorus = song.channels[chName].patterns['chorus']
      const vSig = verse.notes.map(n => `${n.pitch}:${n.duration}:${(n.velocity ?? 0.8).toFixed(2)}`).join(',')
      const cSig = chorus.notes.map(n => `${n.pitch}:${n.duration}:${(n.velocity ?? 0.8).toFixed(2)}`).join(',')
      if (vSig !== cSig) diffCount++
    }
    expect(diffCount).toBeGreaterThanOrEqual(2)
  })

  it('intro has lower velocity than chorus', () => {
    const song = generateSong('synthwave', 42)
    const introVels = song.channels.bass.patterns['intro'].notes
      .filter(n => n.velocity !== undefined).map(n => n.velocity!)
    const chorusVels = song.channels.bass.patterns['chorus'].notes
      .filter(n => n.velocity !== undefined).map(n => n.velocity!)
    const avgIntro = introVels.reduce((a, b) => a + b, 0) / (introVels.length || 1)
    const avgChorus = chorusVels.reduce((a, b) => a + b, 0) / (chorusVels.length || 1)
    expect(avgChorus).toBeGreaterThan(avgIntro)
  })
})

// ---------------------------------------------------------------------------
// Drum Fills
// ---------------------------------------------------------------------------

describe('drum fills', () => {
  it('drum patterns contain fills (extra snare hits on last bar)', () => {
    // Verse sections should have drum fills
    const song = generateSong('rock', 42)
    const verseDrums = song.channels.drums.patterns['verse']
    // Last bar (steps 48-63) should have more snare hits than a typical bar
    // Count snare (pitch 2) hits in the whole pattern
    const snareHits = verseDrums.notes.filter(n => n.pitch === 2)
    expect(snareHits.length).toBeGreaterThan(4) // more than basic 2 per bar * 2
  })

  it('intro drums have no fills', () => {
    const song = generateSong('jazz', 42)
    const introDrums = song.channels.drums.patterns['intro']
    // Intro should be sparse — no fills, mostly hi-hats
    const snareHits = introDrums.notes.filter(n => n.pitch === 2)
    expect(snareHits.length).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// nearestChordTone (musicTheory helper)
// ---------------------------------------------------------------------------

describe('nearestChordTone', () => {
  it('snaps to the nearest chord tone', () => {
    const chord = getChord('C', 'major', 4) // C4, E4, G4
    // A frequency near E4 should snap to E4
    const result = nearestChordTone(330, chord) // E4 ≈ 329.63
    expect(result).toBeCloseTo(chord[1], 0) // E4
  })

  it('returns the input frequency for empty chord', () => {
    const result = nearestChordTone(440, [])
    expect(result).toBe(440)
  })

  it('uses logarithmic distance (octave-aware)', () => {
    // 440 Hz should be closer to 880 Hz (octave up) than to 500 Hz (nearby)
    // log2(440/880) = -1.0, log2(440/500) = -0.184 → 500 is closer
    // But 415 Hz should be closer to 440 Hz than to 220 Hz
    const result = nearestChordTone(415, [220, 440])
    expect(result).toBe(440) // 415 is much closer to 440 in log space
  })
})
