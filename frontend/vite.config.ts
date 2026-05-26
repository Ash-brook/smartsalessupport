import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Dev server runs on :5173. Calls to /api are proxied to the FastAPI backend so the frontend
// can use relative URLs (no CORS surprises). Locally that's localhost:8000; in Docker the
// compose file points VITE_PROXY_TARGET at the backend service.
const proxyTarget = process.env.VITE_PROXY_TARGET || 'http://localhost:8000'

export default defineConfig({
  plugins: [react()],
  server: {
    host: true, // listen on 0.0.0.0 so it's reachable inside a container
    port: 5173,
    proxy: {
      '/api': proxyTarget,
    },
  },
})
