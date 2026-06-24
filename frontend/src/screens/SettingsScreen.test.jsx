import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SettingsScreen from './SettingsScreen'

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

    render(<SettingsScreen />)

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

    render(<SettingsScreen />)

    await waitFor(() => expect(screen.getByText('openai/gpt-4o')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Remove key'))

    await waitFor(() => expect(screen.getByLabelText('OpenRouter API key')).toBeInTheDocument())
  })
})
