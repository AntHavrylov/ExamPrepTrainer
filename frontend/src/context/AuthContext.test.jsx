import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AuthProvider, useAuth } from './AuthContext'

function Probe() {
  const { token, user, authLoading, login, logout } = useAuth()
  return (
    <div>
      <span data-testid="token">{token || 'none'}</span>
      <span data-testid="user">{user ? user.email : 'none'}</span>
      <span data-testid="loading">{String(authLoading)}</span>
      <button onClick={() => login('a@example.com', 'pass')}>login</button>
      <button onClick={logout}>logout</button>
    </div>
  )
}

describe('AuthContext', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('starts logged out when there is no stored token', () => {
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )
    expect(screen.getByTestId('token')).toHaveTextContent('none')
    expect(screen.getByTestId('loading')).toHaveTextContent('false')
  })

  it('login stores the token and loads the user', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/auth/login') {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ access_token: 'abc123', token_type: 'bearer' }),
          })
        }
        if (url === '/auth/me') {
          return Promise.resolve({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ id: 1, email: 'a@example.com', created_at: '2024-01-01' }),
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    )

    screen.getByText('login').click()

    await waitFor(() => expect(screen.getByTestId('token')).toHaveTextContent('abc123'))
    expect(screen.getByTestId('user')).toHaveTextContent('a@example.com')
    expect(localStorage.getItem('prep_trainer_token')).toBe('abc123')
  })
})
