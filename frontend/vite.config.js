import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const BACKEND_URL = 'http://127.0.0.1:8001'

// GitHub Pages serves this as a project page (https://<user>.github.io/ExamPrepTrainer/),
// not a custom domain, so the production build needs assets rooted at /ExamPrepTrainer/.
// Dev server and tests are unaffected (served from /).
const GITHUB_PAGES_BASE = '/ExamPrepTrainer/'

// https://vite.dev/config/
export default defineConfig(({ command }) => ({
  base: command === 'build' ? GITHUB_PAGES_BASE : '/',
  plugins: [react()],
  server: {
    proxy: {
      '/auth': BACKEND_URL,
      '/sections': BACKEND_URL,
      '/documents': BACKEND_URL,
      '/ai': BACKEND_URL,
      '/sessions': BACKEND_URL,
      '/settings': BACKEND_URL,
      '/question-bank': BACKEND_URL,
      '/health': BACKEND_URL,
    },
    // WSL2 + a /mnt/* (9p/DrvFs) project path doesn't deliver inotify events,
    // so Vite's watcher misses edits without polling.
    watch: {
      usePolling: true,
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/setupTests.js',
    globals: true,
  },
}))
