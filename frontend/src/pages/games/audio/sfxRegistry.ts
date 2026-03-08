/**
 * sfxRegistry — Maps each game's events to SFX effect names.
 *
 * Each game has a set of named events (place, win, deal, etc.) that map to
 * effect names in SFX_CATALOG. Games trigger effects by event name; the
 * registry resolves to the actual effect recipe.
 */

/** Event name → effect name. */
type GameSFXMap = Record<string, string>

/**
 * All 37 games with their event→effect mappings.
 */
export const SFX_REGISTRY: Record<string, GameSFXMap> = {
  // ---- Strategy ----
  'tic-tac-toe': {
    place: 'piece_place', win: 'victory_fanfare', lose: 'defeat_tone',
    draw: 'success_small', invalid: 'error_buzz',
  },
  'chess': {
    move: 'piece_slide', capture: 'piece_capture', check: 'warning_beep',
    checkmate: 'victory_fanfare', castle: 'piece_slide',
  },
  'checkers': {
    move: 'piece_slide', jump: 'piece_capture', king: 'level_up', win: 'victory_fanfare',
  },
  'connect-four': {
    drop: 'piece_drop', win: 'victory_fanfare', draw: 'success_small',
  },
  'backgammon': {
    roll: 'dice_roll', move: 'piece_slide', capture: 'piece_capture', win: 'victory_fanfare',
  },
  'ultimate-tic-tac-toe': {
    place: 'piece_place', board_won: 'success_small', win: 'victory_fanfare',
  },

  // ---- Puzzle ----
  '2048': {
    slide: 'tile_slide', merge: 'tile_merge', win: 'victory_fanfare', lose: 'defeat_tone',
  },
  'minesweeper': {
    reveal: 'tile_click', flag: 'ui_toggle', mine: 'explosion', win: 'victory_fanfare',
  },
  'sudoku': {
    enter: 'tile_click', error: 'error_buzz', row_complete: 'success_small', win: 'victory_fanfare',
  },
  'mahjong': {
    select: 'tile_click', match: 'success_small', win: 'victory_fanfare',
  },
  'nonogram': {
    fill: 'tile_click', mark: 'ui_toggle', row_done: 'success_small', win: 'victory_fanfare',
  },
  'memory': {
    flip: 'card_flip', match: 'success_chime', mismatch: 'error_buzz', win: 'victory_fanfare',
  },

  // ---- Word ----
  'wordle': {
    key: 'key_press', correct: 'letter_correct', wrong: 'letter_wrong',
    win: 'word_reveal', invalid: 'error_buzz',
  },
  'hangman': {
    correct: 'letter_correct', wrong: 'letter_wrong', win: 'victory_fanfare', lose: 'defeat_tone',
  },

  // ---- Arcade ----
  'snake': {
    eat: 'collect_food', die: 'collision', level: 'level_up',
  },
  'dino-runner': {
    jump: 'jump', land: 'land', die: 'collision', score: 'collect_coin',
  },
  'space-invaders': {
    fire: 'laser_fire', hit: 'explosion_small', die: 'explosion', score: 'collect_coin',
  },
  'lode-runner': {
    dig: 'explosion_small', collect: 'collect_coin', die: 'collision', level: 'level_up',
  },
  'centipede': {
    fire: 'laser_fire', hit: 'explosion_small', die: 'collision',
  },
  'plinko': {
    drop: 'piece_drop', bounce: 'peg_bounce', land: 'ball_land', win: 'collect_coin',
  },

  // ---- Cards: Solitaire ----
  'solitaire': {
    pickup: 'card_slide', place: 'card_place', flip: 'card_flip',
    autocomplete: 'level_up', win: 'victory_fanfare',
  },
  'freecell': {
    pickup: 'card_slide', place: 'card_place', flip: 'card_flip',
    autocomplete: 'level_up', win: 'victory_fanfare',
  },

  // ---- Cards: Trick-Taking ----
  'hearts': {
    play: 'card_place', trick_won: 'success_small', hand_won: 'success_chime',
  },
  'spades': {
    play: 'card_place', trick_won: 'success_small', hand_won: 'success_chime',
  },
  'euchre': {
    play: 'card_place', trick_won: 'success_small', hand_won: 'success_chime',
  },
  'bridge': {
    play: 'card_place', trick_won: 'success_small', hand_won: 'success_chime',
  },

  // ---- Cards: Rummy ----
  'gin-rummy': {
    draw: 'card_flip', meld: 'success_small', knock: 'ui_confirm', gin: 'victory_fanfare',
  },
  'rummy-500': {
    draw: 'card_flip', meld: 'success_small', knock: 'ui_confirm', gin: 'victory_fanfare',
  },
  'canasta': {
    draw: 'card_flip', meld: 'success_small', knock: 'ui_confirm', gin: 'victory_fanfare',
  },

  // ---- Cards: Casino ----
  'blackjack': {
    deal: 'card_deal', hit: 'card_flip', bust: 'error_buzz',
    blackjack: 'victory_fanfare', bet: 'collect_coin',
  },
  'video-poker': {
    deal: 'card_deal', hold: 'ui_select', draw: 'card_flip',
    win: 'success_chime', jackpot: 'victory_fanfare',
  },
  'texas-holdem': {
    deal: 'card_deal', bet: 'collect_coin', fold: 'card_slide',
    reveal: 'card_flip', win: 'success_chime',
  },

  // ---- Cards: Classic ----
  'crazy-eights': {
    play: 'card_place', draw: 'card_deal', match: 'success_small',
  },
  'war': {
    deal: 'card_deal', flip: 'card_flip', win_round: 'success_small', war: 'warning_beep',
  },
  'go-fish': {
    play: 'card_place', draw: 'card_deal', match: 'success_small',
  },
  'speed': {
    play: 'card_place', flip: 'card_flip', stall: 'warning_beep', win: 'victory_fanfare',
  },
  'spoons': {
    play: 'card_place', discard: 'card_deal', grab: 'collect_coin',
    four_of_kind: 'success_chime', letter: 'error_buzz',
  },
  'cribbage': {
    play: 'card_place', peg: 'ui_click', fifteen: 'success_small', go: 'ui_confirm',
  },
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/** Get the event→effect map for a game. Returns undefined for unknown games. */
export function getGameSFXMap(gameId: string): GameSFXMap | undefined {
  return SFX_REGISTRY[gameId]
}

/** Get all game IDs that have SFX mappings. */
export function getRegisteredGameIds(): string[] {
  return Object.keys(SFX_REGISTRY)
}

/** Get the set of all unique effect names referenced across all games. */
export function getAllMappedEffects(): Set<string> {
  const effects = new Set<string>()
  for (const events of Object.values(SFX_REGISTRY)) {
    for (const effect of Object.values(events)) {
      effects.add(effect)
    }
  }
  return effects
}
