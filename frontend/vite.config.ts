/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
// Note: App version is now fetched from backend /api/version endpoint at runtime
// to avoid Vite cache issues when git tags change
export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    include: ['src/**/*.test.{ts,tsx}'],
  },
  server: {
    port: 5173,
    strictPort: true, // Fail if port 5173 is already in use
    allowedHosts: ['tradebot.romerotechsolutions.com'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true,
        timeout: 60000, // 60 second timeout (portfolio endpoint needs time to fetch many prices)
      },
      '/static': {
        target: 'http://127.0.0.1:8100',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://127.0.0.1:8100',
        ws: true,
      },
    },
  },
})
