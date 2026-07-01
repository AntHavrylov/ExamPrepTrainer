import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// API_BASE_URL is read from import.meta.env at module load time, so each
// case needs a fresh module import after stubbing the env var.
describe('apiUrl', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('returns the path unchanged when no base URL is configured', async () => {
    const { apiUrl } = await import('./api.js')
    expect(apiUrl('/auth/login')).toBe('/auth/login')
  })

  it('prefixes the configured base URL onto the path', async () => {
    vi.stubEnv('VITE_API_BASE_URL', 'https://backend.example.com')
    const { apiUrl } = await import('./api.js')
    expect(apiUrl('/auth/login')).toBe('https://backend.example.com/auth/login')
  })
})
