import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { execFileSync } from 'child_process'

// Get git version at build time using execFileSync (safe - no shell, no user input)
function getGitVersion(): string {
  try {
    return execFileSync('git', ['describe', '--tags', '--always'], { encoding: 'utf-8' }).trim()
  } catch {
    return 'dev'
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: {
    __APP_VERSION__: JSON.stringify(getGitVersion()),
  },
  server: {
    port: 5173,
    strictPort: true, // Fail if port 5173 is already in use
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true,
        timeout: 60000, // 60 second timeout (portfolio endpoint needs time to fetch many prices)
      },
      '/ws': {
        target: 'ws://127.0.0.1:8100',
        ws: true,
      },
    },
  },
})
