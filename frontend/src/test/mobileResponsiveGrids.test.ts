import { describe, it, expect } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative } from 'node:path';
import { readdirSync, readFileSync, statSync } from 'node:fs';

/**
 * Mobile-responsiveness guard for CSS-grid layouts.
 *
 * Why this exists: UI (especially modals and the form sections they render)
 * caused horizontal ("sideways") scrolling on phones because multi-column grids
 * (`grid-cols-2`, `grid-cols-3`, ...) were applied at *every* breakpoint,
 * including the smallest. On a narrow viewport those columns crammed wide form
 * fields / mono-formatted values into tiny cells and pushed content past the
 * screen edge.
 *
 * The fix is to start single-column on mobile and only widen at a breakpoint,
 * e.g. `grid grid-cols-1 sm:grid-cols-2`. This test fails if any component
 * reintroduces a bare (non-breakpoint-prefixed) multi-column grid.
 *
 * Scope is modal components (`*Modal*.tsx`) AND the form `*Section.tsx`
 * components they render (e.g. StrategyConfigSection, BudgetSection,
 * DexConfigSection are rendered inside the bot edit modal). An earlier
 * modal-file-only version of this test missed the sections and let real
 * overflow ship. We deliberately do NOT police every component: game boards
 * (tic-tac-toe `grid-cols-3`, sudoku `grid-cols-9`, 2048 `grid-cols-4`, ...)
 * are intentionally fixed-geometry grids, not overflow bugs. Other dashboard
 * surfaces can adopt the same `grid-cols-1 sm:grid-cols-N` pattern as a separate
 * effort; this guard protects the modal/form surfaces that caused the reported
 * sideways-scrolling.
 *
 * jsdom has no layout engine, so we cannot measure real pixel overflow here;
 * this scans the source for the responsive class pattern instead, which is a
 * durable regression guard for the class that caused the bug.
 *
 * Intentional exceptions (e.g. a row of small fixed-size chips, or a few short
 * read-only values that genuinely fit on mobile) must opt out explicitly by
 * putting the marker `mobile-cols-ok` in a comment on the grid line or the line
 * directly above it.
 */

const srcDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const OPT_OUT = 'mobile-cols-ok';
// A bare (non-breakpoint-prefixed) grid-cols-2..9 — i.e. that many columns on
// the smallest viewport.
const BARE_MULTICOL = /(?<![:\w-])grid-cols-[2-9]/;
// A breakpoint-prefixed grid-cols (sm:/md:/lg:/xl:/2xl:) — proof the author
// gave the grid responsive treatment (e.g. `grid-cols-2 md:grid-cols-4` drops
// to 2 columns before mobile, which is acceptable). Only grids with NO
// responsive variant at all are flagged.
const HAS_BREAKPOINT_COLS = /(?:sm|md|lg|xl|2xl):grid-cols-/;

// Modal components and the form-section components rendered inside them.
const IN_SCOPE = /(Modal[\w.]*|Section)\.tsx$/;

function collectScopedFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    if (entry === 'node_modules' || entry === 'test') continue;
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...collectScopedFiles(full));
    } else if (IN_SCOPE.test(entry) && !entry.endsWith('.test.tsx')) {
      out.push(full);
    }
  }
  return out;
}

describe('mobile responsive grids', () => {
  const files = collectScopedFiles(srcDir);

  it('finds modal/section files to scan', () => {
    expect(files.length).toBeGreaterThan(15);
  });

  it('has no non-responsive multi-column grids', () => {
    const violations: string[] = [];
    for (const file of files) {
      const lines = readFileSync(file, 'utf8').split('\n');
      lines.forEach((line, i) => {
        // opt-out marker may sit on the grid line itself or the line above it
        if (line.includes(OPT_OUT) || (i > 0 && lines[i - 1].includes(OPT_OUT))) return;
        if (BARE_MULTICOL.test(line) && !HAS_BREAKPOINT_COLS.test(line)) {
          violations.push(`${relative(srcDir, file)}:${i + 1}  ${line.trim()}`);
        }
      });
    }
    expect(
      violations,
      `Grids must start single-column on mobile (e.g. "grid-cols-1 sm:grid-cols-2"). ` +
        `Found non-responsive multi-column grid(s):\n${violations.join('\n')}\n` +
        `If a grid genuinely fits on mobile, add a "${OPT_OUT}" comment on that line or the line above it.`,
    ).toEqual([]);
  });
});

describe('bot edit condition builder mobile containment', () => {
  // The bot edit modal scrolled sideways on phones because the condition builder
  // (fixed-width selects in one flex row) was wider than the screen and stretched
  // the shared scroll area. The rows must wrap on small screens so they fit, and
  // the builder scrolls horizontally as a backstop for any still-wide nested row.
  const src = readFileSync(join(srcDir, 'components/trading/AdvancedConditionBuilder.tsx'), 'utf8');

  it('condition rows wrap on small screens', () => {
    expect(
      /flex flex-wrap items-center gap-2 p-2/.test(src),
      'the condition row must use flex-wrap so its controls stack instead of overflowing',
    ).toBe(true);
  });

  it('builder scrolls horizontally as a backstop', () => {
    expect(
      src.includes('overflow-x-auto'),
      'AdvancedConditionBuilder should scroll horizontally so nested wide rows stay reachable',
    ).toBe(true);
  });
});
