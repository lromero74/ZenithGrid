import { describe, it, expect } from 'vitest';
import { fileURLToPath } from 'node:url';
import { dirname, join, relative } from 'node:path';
import { readdirSync, readFileSync, statSync } from 'node:fs';

/**
 * Mobile-responsiveness guard for modals.
 *
 * Why this exists: modals were causing horizontal ("sideways") scrolling on
 * phones because multi-column CSS-grid layouts (`grid-cols-2`, `grid-cols-3`,
 * ...) were applied at *every* breakpoint, including the smallest. On a narrow
 * viewport those columns crammed wide form fields / mono-formatted values into
 * tiny cells and pushed content past the screen edge.
 *
 * The fix is to start single-column on mobile and only widen at a breakpoint,
 * e.g. `grid grid-cols-1 sm:grid-cols-2`. This test fails if any modal
 * reintroduces a bare (non-breakpoint-prefixed) multi-column grid.
 *
 * jsdom has no layout engine, so we cannot measure real pixel overflow here;
 * this scans the source for the responsive class pattern instead, which is a
 * durable regression guard for the class that caused the bug.
 *
 * Intentional exceptions (e.g. a row of small fixed-size chips that genuinely
 * fits on mobile) must opt out explicitly by putting the marker `mobile-cols-ok`
 * in a comment on the same line.
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

function collectModalFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...collectModalFiles(full));
    } else if (/Modal.*\.tsx$/.test(entry) && !entry.endsWith('.test.tsx')) {
      out.push(full);
    }
  }
  return out;
}

describe('modal mobile responsiveness', () => {
  const modalFiles = collectModalFiles(srcDir);

  it('finds modal components to scan', () => {
    expect(modalFiles.length).toBeGreaterThan(10);
  });

  it('has no non-responsive multi-column grids in modals', () => {
    const violations: string[] = [];
    for (const file of modalFiles) {
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
      `Modal grids must start single-column on mobile (e.g. "grid-cols-1 sm:grid-cols-2"). ` +
        `Found non-responsive multi-column grid(s):\n${violations.join('\n')}\n` +
        `If a grid genuinely fits on mobile, add a "${OPT_OUT}" comment on that line.`,
    ).toEqual([]);
  });
});
