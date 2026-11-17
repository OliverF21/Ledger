import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
    host: true,
    proxy: {
      '/api': {
        target: process.env.VITE_API_BASE_URL || 'http://localhost:8000',
        changeOrigin: true,
        // The backend only treats a loopback peer as this computer. Without
        // the original client address, every browser that hits this proxy
        // looks like 127.0.0.1 and can open a no-account session.
        xfwd: true,
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          'recharts-vendor': ['recharts'],
          'react-vendor': ['react', 'react-dom']
        }
      }
    }
  }
})
