/**
 * sfxCatalog — 53 procedural sound effect recipes.
 *
 * Each recipe is a function that composes SFXEngine primitives with specific
 * parameters. Every play call receives a random variation (0–1) so no two
 * plays sound identical.
 *
 * Categories:
 *   1. UI Feedback (6)
 *   2. Card & Paper (6)
 *   3. Board & Piece (8)
 *   4. Tonal Feedback (10)
 *   5. Arcade Action (10)
 *   6. Word Game (4)
 *   7. Ambient/Nature Loops (6)
 *   8. Game Over Jingles (3)
 */

import { SFXEngine } from './sfxEngine'

const J = SFXEngine.jitter

export type SFXRecipe = (engine: SFXEngine, time: number, variation: number) => void

// ===========================================================================
// Category 1: UI Feedback
// ===========================================================================

function ui_click(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.03, 'highpass', J(4000, v, 0.08), 1, 0.3)
  e.tonePulse(t, J(2000, v, 0.1), 0.02, 'sine', 0.25)
}

function ui_select(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(880, v, 0.05), 0.08, 'sine', 0.3, { attack: 0.005, decay: 0.03, sustain: 0.5, release: 0.03 })
}

function ui_error(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(200, v, 0.08), 0.15, 'sawtooth', 0.3)
  e.tonePulse(t + 0.05, J(180, v, 0.08), 0.1, 'sawtooth', 0.25)
}

function ui_confirm(e: SFXEngine, t: number, v: number): void {
  e.pitchSweep(t, J(660, v, 0.05), J(880, v, 0.05), 0.1, 'sine', 0.35)
}

function ui_hover(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.015, 'highpass', J(6000, v, 0.08), 1, 0.15)
}

function ui_toggle(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(1200, v, 0.08), 0.03, 'square', 0.2)
}

// ===========================================================================
// Category 2: Card & Paper
// ===========================================================================

function card_flip(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.15, 'bandpass', J(3000, v, 0.13), 2, 0.3)
  e.pitchSweep(t + J(0.01, v, 0.5), 6000, 2000, 0.08, 'sine', 0.15)
}

function card_deal(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.08, 'highpass', J(4000, v, 0.12), 1.5, J(0.3, v, 0.15))
}

function card_shuffle(e: SFXEngine, t: number, v: number): void {
  const count = 5 + Math.floor(v * 3) // 5–8 cards
  for (let i = 0; i < count; i++) {
    const offset = i * J(0.07, v, 0.3)
    card_deal(e, t + offset, Math.random())
  }
}

function card_place(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.06, 'bandpass', J(2000, v, 0.1), 1.5, 0.25)
  e.tonePulse(t, J(400, v, 0.1), 0.04, 'sine', 0.15)
}

function card_slide(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, J(0.3, v, 0.2), 'highpass', 2000, 1, 0.25, 1500)
}

function card_fan(e: SFXEngine, t: number, v: number): void {
  for (let i = 0; i < 4; i++) {
    const offset = i * J(0.06, v, 0.15)
    const gain_scale = 0.15 + i * 0.05
    e.noiseBurst(t + offset, 0.12, 'bandpass', J(3000, v, 0.1), 2, gain_scale)
  }
}

// ===========================================================================
// Category 3: Board & Piece
// ===========================================================================

function piece_place(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.08, 'lowpass', J(1500, v, 0.13), 1, 0.3)
  e.tonePulse(t, J(300, v, 0.12), 0.05, 'sine', 0.2)
}

function piece_capture(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.05, 'bandpass', J(3000, v, 0.1), 2, 0.3)
  e.pitchSweep(t, J(800, v, 0.1), J(400, v, 0.1), 0.1, 'sine', 0.3)
}

function piece_slide(e: SFXEngine, t: number, v: number): void {
  e.filteredNoise(t, 0.2, 'bandpass', J(1000, v, 0.3), 2, 0.2)
}

function piece_drop(e: SFXEngine, t: number, v: number): void {
  e.pitchSweep(t, J(600, v, 0.15), J(200, v, 0.15), 0.12, 'sine', 0.35)
  e.noiseBurst(t + 0.08, 0.06, 'lowpass', J(800, v, 0.12), 1, 0.25)
}

function tile_click(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(1500, v, 0.08), 0.03, 'triangle', 0.25)
  e.noiseBurst(t, 0.02, 'highpass', J(5000, v, 0.1), 1, 0.15)
}

function tile_slide(e: SFXEngine, t: number, v: number): void {
  e.filteredNoise(t, 0.15, 'bandpass', J(2000, v, 0.2), 2, 0.2)
}

function tile_merge(e: SFXEngine, t: number, v: number): void {
  e.fmTone(t, J(440, v, 0.05), 2.5, J(100, v, 0.15), 0.2, 0.35)
}

function dice_roll(e: SFXEngine, t: number, v: number): void {
  const count = 20 + Math.floor(v * 10) // 20–30 clicks
  for (let i = 0; i < count; i++) {
    const progress = i / count
    const offset = progress * 1.0 + (Math.random() - 0.5) * J(0.03, v, 0.4)
    const amp = 0.3 * Math.exp(-progress * 3) // exponential decay
    e.noiseBurst(t + Math.max(0, offset), 0.03, 'bandpass', J(2500, v, 0.15), 2, amp)
  }
}

// ===========================================================================
// Category 4: Tonal Feedback
// ===========================================================================

function success_chime(e: SFXEngine, t: number, v: number): void {
  e.fmTone(t, J(880, v, 0.03), 3, 150, 0.6, 0.35)
  e.tonePulse(t + 0.1, J(1320, v, 0.03), 0.4, 'sine', 0.25,
    { attack: 0.01, decay: 0.1, sustain: 0.4, release: 0.2 })
}

function success_small(e: SFXEngine, t: number, v: number): void {
  e.pitchSweep(t, J(880, v, 0.05), J(1100, v, 0.05), 0.2, 'sine', 0.3)
}

function error_buzz(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(150, v, 0.1), 0.2, 'sawtooth', 0.35)
}

function warning_beep(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(1000, v, 0.05), 0.1, 'square', 0.25)
  e.tonePulse(t + 0.15, J(1000, v, 0.05), 0.1, 'square', 0.25)
}

function level_up(e: SFXEngine, t: number, v: number): void {
  const base = J(440, v, 0.05)
  e.tonePulse(t, base, 0.12, 'sine', 0.3)
  e.tonePulse(t + 0.12, base * 1.25, 0.12, 'sine', 0.3)
  e.tonePulse(t + 0.24, base * 1.5, 0.15, 'sine', 0.35)
}

function victory_fanfare(e: SFXEngine, t: number, v: number): void {
  const base = J(330, v, 0.03)
  const ratios = [1, 4/3, 5/3, 2] // 330, 440, 550, 660
  for (let i = 0; i < 4; i++) {
    e.fmTone(t + i * 0.2, base * ratios[i], 2, 120, 0.3, 0.3)
  }
}

function defeat_tone(e: SFXEngine, t: number, v: number): void {
  e.pitchSweep(t, J(400, v, 0.1), 150, 0.6, 'sawtooth', 0.3)
}

function countdown_tick(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(800, v, 0.03), 0.05, 'sine', 0.25)
}

function countdown_urgent(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(1200, v, 0.05), 0.03, 'square', 0.25)
  e.tonePulse(t + 0.08, J(1200, v, 0.05), 0.03, 'square', 0.25)
}

function streak_milestone(e: SFXEngine, t: number, v: number): void {
  e.fmTone(t, J(660, v, 0.03), 2, J(200, v, 0.2), 0.4, 0.35)
  success_chime(e, t + 0.2, v)
}

// ===========================================================================
// Category 5: Arcade Action
// ===========================================================================

function laser_fire(e: SFXEngine, t: number, v: number): void {
  e.pitchSweep(t, J(2500, v, 0.15), 300, 0.2, 'sawtooth', 0.35)
}

function explosion(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 2.0, 'lowpass', J(4000, v, 0.2), 1, 0.4, 800)
  e.tonePulse(t + 0.05, J(80, v, 0.1), 1.5, 'sine', 0.35)
  e.noiseBurst(t + 0.1, 1.5, 'bandpass', J(1500, v, 0.15), 2, 0.25)
}

function explosion_small(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.5, 'lowpass', J(3000, v, 0.15), 1, 0.35, 1000)
  e.tonePulse(t, J(100, v, 0.1), 0.3, 'sine', 0.25)
}

function jump(e: SFXEngine, t: number, v: number): void {
  e.pitchSweep(t, 200, J(800, v, 0.06), 0.12, 'sine', 0.35)
  e.noiseBurst(t, 0.03, 'highpass', 3000, 1, 0.15)
}

function land(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.08, 'lowpass', J(600, v, 0.17), 1, 0.3)
  e.tonePulse(t, J(150, v, 0.1), 0.06, 'sine', 0.2)
}

function collect_coin(e: SFXEngine, t: number, v: number): void {
  e.fmTone(t, J(1200, v, 0.05), 2.5, 100, 0.3, 0.3)
  e.fmTone(t + 0.05, J(1800, v, 0.05), 2, 80, 0.2, 0.25)
}

function collect_food(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.1, 'bandpass', J(1000, v, 0.1), 2, 0.25)
  e.tonePulse(t, J(600, v, 0.1), 0.08, 'sine', 0.25)
}

function collision(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.1, 'bandpass', J(2000, v, 0.15), 2, 0.35)
  e.pitchSweep(t, J(400, v, 0.1), 150, 0.08, 'sine', 0.3)
}

function peg_bounce(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(1500, v, 0.12), 0.04, 'triangle', 0.25)
  e.noiseBurst(t, 0.02, 'highpass', J(4000, v, 0.1), 1, 0.15)
}

function ball_land(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.1, 'lowpass', J(1000, v, 0.15), 1, 0.3)
  e.pitchSweep(t, J(200, v, 0.15), 100, 0.08, 'sine', 0.2)
}

// ===========================================================================
// Category 6: Word Game
// ===========================================================================

function key_press(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, 0.025, 'highpass', J(5000, v, 0.1), 1, 0.2)
  e.tonePulse(t, J(1800, v, 0.05), 0.015, 'sine', 0.12)
}

function letter_correct(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(880, v, 0.05), 0.15, 'sine', 0.3)
}

function letter_wrong(e: SFXEngine, t: number, v: number): void {
  e.tonePulse(t, J(220, v, 0.08), 0.12, 'sawtooth', 0.25)
}

function word_reveal(e: SFXEngine, t: number, v: number): void {
  const base = J(440, v, 0.05)
  for (let i = 0; i < 5; i++) {
    const freq = base * (1 + i * 0.2) // ascending: 440→528→616→704→792→880
    e.tonePulse(t + i * 0.08, freq, 0.12, 'sine', 0.25)
  }
}

// ===========================================================================
// Category 7: Ambient/Nature Loops
// ===========================================================================

function ambient_wind(e: SFXEngine, t: number, v: number): void {
  e.filteredNoise(t, 999, 'lowpass', J(300, v, 0.33), 1, 0.12, J(0.5, v, 0.4), 50)
  e.filteredNoise(t, 999, 'lowpass', J(800, v, 0.13), 0.8, 0.08, J(0.3, v, 0.4), 100)
  e.filteredNoise(t, 999, 'lowpass', J(2000, v, 0.05), 0.5, 0.05, J(0.7, v, 0.3), 200)
}

function ambient_rain(e: SFXEngine, t: number, v: number): void {
  e.filteredNoise(t, 999, 'highpass', 5000, 0.5, 0.12)
  e.filteredNoise(t, 999, 'bandpass', 2000, 1, 0.15, J(4, v, 0.25), 300)
  e.filteredNoise(t, 999, 'lowpass', 500, 0.5, 0.08)
}

function ambient_thunder(e: SFXEngine, t: number, v: number): void {
  e.noiseBurst(t, J(3.0, v, 0.2), 'lowpass', 4000, 1, 0.4, 800)
  e.tonePulse(t + J(0.2, v, 0.5), J(100, v, 0.1), 2.0, 'sine', 0.3)
}

function ambient_crickets(e: SFXEngine, t: number, v: number): void {
  // Burst of chirps — caller should loop/repeat as needed
  const chirpCount = 3 + Math.floor(v * 3) // 3–6 chirps
  for (let i = 0; i < chirpCount; i++) {
    const offset = i * 0.14 + (Math.random() - 0.5) * 0.02
    e.tonePulse(t + offset, J(5000, v, 0.05), 0.04, 'sine', 0.12)
  }
}

function ambient_birds(e: SFXEngine, t: number, v: number): void {
  const chirpCount = 2 + Math.floor(v * 3) // 2–5 chirps
  for (let i = 0; i < chirpCount; i++) {
    const offset = i * 0.15 + (Math.random() - 0.5) * 0.03
    const baseFreq = J(3000, v, 0.17)
    e.pitchSweep(t + offset, baseFreq, baseFreq * 1.5, 0.05, 'sine', 0.15)
    e.pitchSweep(t + offset + 0.05, baseFreq * 1.5, baseFreq, 0.05, 'sine', 0.12)
  }
}

function ambient_water(e: SFXEngine, t: number, v: number): void {
  e.filteredNoise(t, 999, 'highpass', 800, 0.5, 0.1, J(1, v, 0.3), 100)
  e.filteredNoise(t, 999, 'lowpass', 3000, 0.5, 0.08, J(3, v, 0.33), 200)
}

// ===========================================================================
// Category 8: Game Over Jingles
// ===========================================================================

/** Win jingle (~3s): Ascending C major arpeggio with FM bell tones + octave shimmer. */
function gameover_win(e: SFXEngine, t: number, v: number): void {
  const base = J(262, v, 0.02) // C4
  // Ascending C major arpeggio: C E G C5
  const notes = [base, base * 5 / 4, base * 3 / 2, base * 2]
  for (let i = 0; i < notes.length; i++) {
    e.fmTone(t + i * 0.22, notes[i], 3, J(120, v, 0.1), 0.5, 0.3)
  }
  // Octave shimmer on top
  e.fmTone(t + 1.0, base * 2, 2.5, 80, 0.8, 0.25)
  e.fmTone(t + 1.2, base * 2.5, 2, 60, 0.6, 0.2)
  // Final triumphant chord
  e.fmTone(t + 1.6, base * 2, 3, 100, 1.0, 0.3)
  e.fmTone(t + 1.6, base * 2.5, 3, 80, 1.0, 0.22)
  e.fmTone(t + 1.6, base * 3, 2, 60, 1.0, 0.18)
}

/** Lose jingle (~2.5s): Descending minor phrase with sawtooth + low rumble. */
function gameover_lose(e: SFXEngine, t: number, v: number): void {
  const base = J(330, v, 0.03) // E4
  // Descending minor: E D C B3
  const notes = [base, base * 9 / 10, base * 4 / 5, base * 3 / 4]
  for (let i = 0; i < notes.length; i++) {
    e.tonePulse(t + i * 0.25, notes[i], 0.35, 'sawtooth', 0.25,
      { attack: 0.01, decay: 0.08, sustain: 0.5, release: 0.15 })
  }
  // Low rumble
  e.tonePulse(t + 1.0, J(80, v, 0.1), 1.2, 'sine', 0.2)
  // Final descending sweep
  e.pitchSweep(t + 1.3, J(250, v, 0.05), 80, 0.8, 'sawtooth', 0.2)
}

/** Draw jingle (~2s): Neutral resolved phrase with perfect 4th/5th intervals. */
function gameover_draw(e: SFXEngine, t: number, v: number): void {
  const base = J(294, v, 0.02) // D4
  // Neutral phrase: D G D5 (P4 up, P4 up)
  e.fmTone(t, base, 2.5, J(80, v, 0.1), 0.4, 0.28)
  e.fmTone(t + 0.3, base * 4 / 3, 2.5, J(80, v, 0.1), 0.4, 0.28) // P4
  e.fmTone(t + 0.6, base * 3 / 2, 2, J(60, v, 0.1), 0.5, 0.25) // P5 from root
  // Resolved unison
  e.fmTone(t + 1.0, base, 2, 80, 0.7, 0.25)
  e.fmTone(t + 1.0, base * 3 / 2, 2, 60, 0.7, 0.2)
}

// ===========================================================================
// Exports
// ===========================================================================

/** All 53 effect recipes indexed by name. */
export const SFX_CATALOG: Record<string, SFXRecipe> = {
  // UI Feedback
  ui_click, ui_select, ui_error, ui_confirm, ui_hover, ui_toggle,
  // Card & Paper
  card_flip, card_deal, card_shuffle, card_place, card_slide, card_fan,
  // Board & Piece
  piece_place, piece_capture, piece_slide, piece_drop,
  tile_click, tile_slide, tile_merge, dice_roll,
  // Tonal Feedback
  success_chime, success_small, error_buzz, warning_beep, level_up,
  victory_fanfare, defeat_tone, countdown_tick, countdown_urgent, streak_milestone,
  // Arcade Action
  laser_fire, explosion, explosion_small, jump, land,
  collect_coin, collect_food, collision, peg_bounce, ball_land,
  // Word Game
  key_press, letter_correct, letter_wrong, word_reveal,
  // Ambient/Nature
  ambient_wind, ambient_rain, ambient_thunder, ambient_crickets, ambient_birds, ambient_water,
  // Game Over
  gameover_win, gameover_lose, gameover_draw,
}

/** Category groupings for UI and testing. */
export const EFFECT_CATEGORIES: Record<string, string[]> = {
  'UI Feedback': ['ui_click', 'ui_select', 'ui_error', 'ui_confirm', 'ui_hover', 'ui_toggle'],
  'Card & Paper': ['card_flip', 'card_deal', 'card_shuffle', 'card_place', 'card_slide', 'card_fan'],
  'Board & Piece': ['piece_place', 'piece_capture', 'piece_slide', 'piece_drop', 'tile_click', 'tile_slide', 'tile_merge', 'dice_roll'],
  'Tonal Feedback': ['success_chime', 'success_small', 'error_buzz', 'warning_beep', 'level_up', 'victory_fanfare', 'defeat_tone', 'countdown_tick', 'countdown_urgent', 'streak_milestone'],
  'Arcade Action': ['laser_fire', 'explosion', 'explosion_small', 'jump', 'land', 'collect_coin', 'collect_food', 'collision', 'peg_bounce', 'ball_land'],
  'Word Game': ['key_press', 'letter_correct', 'letter_wrong', 'word_reveal'],
  'Ambient/Nature': ['ambient_wind', 'ambient_rain', 'ambient_thunder', 'ambient_crickets', 'ambient_birds', 'ambient_water'],
  'Game Over': ['gameover_win', 'gameover_lose', 'gameover_draw'],
}
