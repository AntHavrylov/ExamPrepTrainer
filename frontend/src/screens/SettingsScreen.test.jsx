import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider } from '../context/AuthContext'
import { LanguageProvider } from '../context/LanguageContext'
import SettingsScreen from './SettingsScreen'

function renderWithProviders(ui) {
  return render(
    <AuthProvider>
      <LanguageProvider>{ui}</LanguageProvider>
    </AuthProvider>,
  )
}

function mockFetchByPath(handlers) {
  vi.stubGlobal(
    'fetch',
    vi.fn((url, options) => {
      const handler = handlers[url]
      if (!handler) throw new Error(`Unexpected fetch to ${url}`)
      return handler(options)
    }),
  )
}

function jsonResponse(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

describe('SettingsScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('shows the key form when no key is configured', async () => {
    mockFetchByPath({
      '/settings/api-key': () => jsonResponse(200, { has_key: false, model: null }),
      '/settings/models': () =>
        jsonResponse(200, [{ id: 'a/1', name: 'Model A', context_length: null }]),
    })

    renderWithProviders(<SettingsScreen />)

    await waitFor(() => expect(screen.getByLabelText('OpenRouter API key')).toBeInTheDocument())
    expect(screen.getByRole('option', { name: 'Model A' })).toBeInTheDocument()
  })

  it('shows the configured state and reverts to the form after removing the key', async () => {
    mockFetchByPath({
      '/settings/api-key': (options) =>
        options?.method === 'DELETE'
          ? jsonResponse(204, null)
          : jsonResponse(200, { has_key: true, model: 'openai/gpt-4o' }),
      '/settings/models': () => jsonResponse(200, []),
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)

    renderWithProviders(<SettingsScreen />)

    await waitFor(() => expect(screen.getByText('openai/gpt-4o')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Remove key'))

    await waitFor(() => expect(screen.getByLabelText('OpenRouter API key')).toBeInTheDocument())
  })

  it('changing the language select persists it and re-renders the UI in that language', async () => {
    mockFetchByPath({
      '/settings/api-key': () => jsonResponse(200, { has_key: false, model: null }),
      '/settings/models': () => jsonResponse(200, []),
      '/settings/language': (options) => {
        expect(options.method).toBe('PUT')
        expect(JSON.parse(options.body)).toEqual({ language: 'uk' })
        return jsonResponse(200, { id: 1, email: 'a@example.com', language: 'uk', created_at: '2024-01-01' })
      },
    })

    renderWithProviders(<SettingsScreen />)

    await waitFor(() => expect(screen.getByLabelText('OpenRouter API key')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'uk' } })

    await waitFor(() => expect(screen.getByText('Налаштування AI')).toBeInTheDocument())
  })

  it('changing the session length select persists it via the API', async () => {
    mockFetchByPath({
      '/settings/api-key': () => jsonResponse(200, { has_key: false, model: null }),
      '/settings/models': () => jsonResponse(200, []),
      '/settings/session-length': (options) => {
        expect(options.method).toBe('PUT')
        expect(JSON.parse(options.body)).toEqual({ session_length: 10 })
        return jsonResponse(200, {
          id: 1,
          email: 'a@example.com',
          language: 'en',
          session_length: 10,
          created_at: '2024-01-01',
        })
      },
    })

    renderWithProviders(<SettingsScreen />)

    await waitFor(() => expect(screen.getByLabelText('OpenRouter API key')).toBeInTheDocument())

    fireEvent.change(screen.getByLabelText('Session length'), { target: { value: '10' } })

    await waitFor(() =>
      expect(screen.getByLabelText('Session length')).toHaveValue('10'),
    )
  })
})
