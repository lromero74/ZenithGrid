import { describe, expect, test } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..')

describe('hard-refresh loading path', () => {
  test('preloads the direct route chunk before authenticated rendering', () => {
    const appSource = readFileSync(join(frontendRoot, 'src', 'App.tsx'), 'utf8')

    expect(appSource).toContain('initialRouteImporter')
    expect(appSource).toContain('window.location.pathname')
    expect(appSource).toContain('import.meta.env.PROD')
  })

  test('does not classify lucide-react as blocking framework code', () => {
    const configSource = readFileSync(join(frontendRoot, 'vite.config.ts'), 'utf8')

    expect(configSource).toContain("id.includes('/node_modules/lucide-react/')")
    expect(configSource).not.toContain("id.includes('react')")
    expect(configSource).toContain('react-router-dom')
  })
})
