/**
 * Hangman game engine — pure functions, no React dependencies.
 */

import { WORD_LISTS, MAX_WRONG_GUESSES } from './wordLists'

export function selectWord(category: string): string {
  const words = WORD_LISTS[category]
  return words[Math.floor(Math.random() * words.length)]
}

export function getDisplayWord(word: string, guessedLetters: Set<string>): string {
  return word
    .split('')
    .map(letter => guessedLetters.has(letter.toUpperCase()) ? letter : '_')
    .join(' ')
}

export function processGuess(word: string, letter: string): boolean {
  return word.toUpperCase().includes(letter.toUpperCase())
}

export function isGameWon(word: string, guessedLetters: Set<string>): boolean {
  return word.toUpperCase().split('').every(letter => guessedLetters.has(letter.toUpperCase()))
}

export function isGameLost(wrongGuessCount: number): boolean {
  return wrongGuessCount >= MAX_WRONG_GUESSES
}

export function getWrongGuesses(word: string, guessedLetters: Set<string>): number {
  const wordLetters = new Set(word.toUpperCase().split(''))
  let count = 0
  for (const letter of guessedLetters) {
    if (!wordLetters.has(letter.toUpperCase())) count++
  }
  return count
}
