// Single source of truth for USD currency display, mirroring the dateFormat.ts pattern.
// Produces "$1,234.56" (grouped, always 2 decimals, standard "-$1,234.56" for negatives).

const USD_FMT = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

export const formatUsd = (value: number): string => USD_FMT.format(value)
