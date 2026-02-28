/**
 * Progressive SVG hangman figure — draws body parts based on wrong guess count.
 */

interface HangmanDrawingProps {
  wrongGuesses: number
}

const BODY_PARTS = [
  // Head
  <circle key="head" cx="200" cy="70" r="20" className="stroke-slate-300 fill-none" strokeWidth="3" />,
  // Body
  <line key="body" x1="200" y1="90" x2="200" y2="150" className="stroke-slate-300" strokeWidth="3" />,
  // Left arm
  <line key="leftArm" x1="200" y1="110" x2="170" y2="140" className="stroke-slate-300" strokeWidth="3" />,
  // Right arm
  <line key="rightArm" x1="200" y1="110" x2="230" y2="140" className="stroke-slate-300" strokeWidth="3" />,
  // Left leg
  <line key="leftLeg" x1="200" y1="150" x2="170" y2="190" className="stroke-slate-300" strokeWidth="3" />,
  // Right leg
  <line key="rightLeg" x1="200" y1="150" x2="230" y2="190" className="stroke-slate-300" strokeWidth="3" />,
]

export function HangmanDrawing({ wrongGuesses }: HangmanDrawingProps) {
  return (
    <svg viewBox="0 0 300 220" className="w-full max-w-[220px] sm:max-w-[260px]">
      {/* Gallows */}
      <line x1="60" y1="210" x2="160" y2="210" className="stroke-slate-500" strokeWidth="3" />
      <line x1="100" y1="210" x2="100" y2="20" className="stroke-slate-500" strokeWidth="3" />
      <line x1="100" y1="20" x2="200" y2="20" className="stroke-slate-500" strokeWidth="3" />
      <line x1="200" y1="20" x2="200" y2="50" className="stroke-slate-500" strokeWidth="3" />

      {/* Body parts — shown progressively */}
      {BODY_PARTS.slice(0, wrongGuesses)}
    </svg>
  )
}
