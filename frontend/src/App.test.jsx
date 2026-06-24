import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { ACTIVE_SESSION_KEY } from './api'

function jsonResponse(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

describe('App session resume', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
    window.matchMedia = vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn() })
  })

  it('lands directly on the training screen for a session persisted before reload, skipping Sections', async () => {
    localStorage.setItem('prep_trainer_token', 'tok123')
    localStorage.setItem(ACTIVE_SESSION_KEY, '42')

    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/auth/me') {
          return jsonResponse(200, {
            id: 1,
            email: 'a@example.com',
            language: 'en',
            session_length: 5,
            created_at: '2024-01-01T00:00:00Z',
          })
        }
        if (url === '/sessions/42') {
          return jsonResponse(200, {
            id: 42,
            mode: 'technical',
            format: 'quiz',
            difficulty: 'medium',
            target_question_count: 5,
            section_ids: [1],
            started_at: '2024-01-01T00:00:00Z',
            finished_at: null,
            attempts: [
              {
                id: 9,
                question: 'Resumed after reload',
                category: 'technical',
                format: 'quiz',
                options: ['A', 'B'],
                selected_index: null,
                correct_index: null,
                answer: null,
                score: null,
                feedback: null,
                created_at: '2024-01-01T00:00:00Z',
                hint: null,
                explanation: null,
              },
            ],
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    render(<App />)

    await waitFor(() => expect(screen.getByText('Resumed after reload')).toBeInTheDocument())
    expect(screen.queryByText('Your sections')).not.toBeInTheDocument()
  })

  it('resumes the in-progress session after navigating to Settings and back to Train, instead of starting a new one', async () => {
    localStorage.setItem('prep_trainer_token', 'tok123')
    localStorage.setItem(ACTIVE_SESSION_KEY, '42')

    const startSessionSpy = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/auth/me') {
          return jsonResponse(200, {
            id: 1,
            email: 'a@example.com',
            language: 'en',
            session_length: 5,
            created_at: '2024-01-01T00:00:00Z',
          })
        }
        if (url === '/sessions' && options?.method === 'POST') {
          startSessionSpy()
          return jsonResponse(201, { id: 99 })
        }
        if (url === '/settings/api-key') return jsonResponse(200, { has_key: false, model: null })
        if (url === '/settings/models') return jsonResponse(200, [])
        if (url === '/sessions/42') {
          return jsonResponse(200, {
            id: 42,
            mode: 'technical',
            format: 'quiz',
            difficulty: 'medium',
            target_question_count: 5,
            section_ids: [1],
            started_at: '2024-01-01T00:00:00Z',
            finished_at: null,
            attempts: [
              {
                id: 9,
                question: 'In-progress question',
                category: 'technical',
                format: 'quiz',
                options: ['A', 'B'],
                selected_index: null,
                correct_index: null,
                answer: null,
                score: null,
                feedback: null,
                created_at: '2024-01-01T00:00:00Z',
                hint: null,
                explanation: null,
              },
            ],
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    render(<App />)
    await waitFor(() => expect(screen.getByText('In-progress question')).toBeInTheDocument())

    // Navigate away to Settings...
    screen.getByTitle('Settings').click()
    await waitFor(() => expect(screen.queryByText('In-progress question')).not.toBeInTheDocument())

    // ...and back to Train: must resume session 42, not open the new-session form.
    screen.getByTitle('Train').click()
    await waitFor(() => expect(screen.getByText('In-progress question')).toBeInTheDocument())
    expect(startSessionSpy).not.toHaveBeenCalled()
  })

  it('resumes the in-progress session after navigating to Sections and back to Train', async () => {
    localStorage.setItem('prep_trainer_token', 'tok123')
    localStorage.setItem(ACTIVE_SESSION_KEY, '42')

    const startSessionSpy = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/auth/me') {
          return jsonResponse(200, {
            id: 1,
            email: 'a@example.com',
            language: 'en',
            session_length: 5,
            created_at: '2024-01-01T00:00:00Z',
          })
        }
        if (url === '/sessions' && options?.method === 'POST') {
          startSessionSpy()
          return jsonResponse(201, { id: 99 })
        }
        if (url === '/sections') return jsonResponse(200, [])
        if (url === '/sessions/42') {
          return jsonResponse(200, {
            id: 42,
            mode: 'technical',
            format: 'quiz',
            difficulty: 'medium',
            target_question_count: 5,
            section_ids: [1],
            started_at: '2024-01-01T00:00:00Z',
            finished_at: null,
            attempts: [
              {
                id: 9,
                question: 'In-progress question',
                category: 'technical',
                format: 'quiz',
                options: ['A', 'B'],
                selected_index: null,
                correct_index: null,
                answer: null,
                score: null,
                feedback: null,
                created_at: '2024-01-01T00:00:00Z',
                hint: null,
                explanation: null,
              },
            ],
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    render(<App />)
    await waitFor(() => expect(screen.getByText('In-progress question')).toBeInTheDocument())

    // Navigate away to Sections...
    screen.getByTitle('Sections').click()
    await waitFor(() => expect(screen.queryByText('In-progress question')).not.toBeInTheDocument())

    // ...and back to Train: must resume session 42, not open the new-session form.
    screen.getByTitle('Train').click()
    await waitFor(() => expect(screen.getByText('In-progress question')).toBeInTheDocument())
    expect(startSessionSpy).not.toHaveBeenCalled()
  })
})
