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
