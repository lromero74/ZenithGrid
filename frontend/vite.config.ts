import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true, // Fail if port 5173 is already in use
    proxy: {
      '/api': {
        target: 'http://localhost:8100',
        changeOrigin: true,
        timeout: 10000, // 10 second timeout
      },
      '/ws': {
        target: 'ws://localhost:8100',
        ws: true,
      },
    },
  },
})
