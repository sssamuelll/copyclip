import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Test-only config, kept separate from vite.config.ts so the single-file build
// plugin never runs under the test environment.
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
  },
})
