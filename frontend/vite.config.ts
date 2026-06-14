/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
// Note: App version is now fetched from backend /api/version endpoint at runtime
// to avoid Vite cache issues when git tags change
export default defineConfig({
  plugins: [react()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('react') || id.includes('@tanstack/react-query') || id.includes('react-router-dom')) {
            return 'framework'
          }
          // Split the two charting libraries into separate chunks — no page uses
          // both (Positions uses lightweight-charts; Reports/Dashboard use recharts),
          // so this trims each page's load and keeps both chunks under the 500 kB warning.
          if (id.includes('lightweight-charts')) {
            return 'lightweight-charts'
          }
          if (id.includes('recharts')) {
            return 'recharts'
          }
          if (id.includes('lucide-react')) {
            return 'icons'
          }
        },
      },
    },
  },
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
