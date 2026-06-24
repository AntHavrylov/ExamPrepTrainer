import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../context/LanguageContext'
import SummaryScreen from './SummaryScreen'

function renderWithProviders(ui) {
  return render(<LanguageProvider>{ui}</LanguageProvider>)
}

function jsonResponse(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

describe('SummaryScreen', () => {
  it('shows the correct answer for quiz attempts even when the user answered correctly', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/s1') {
          return jsonResponse(200, {
            id: 1,
            mode: 'technical',
            format: 'quiz',
            difficulty: 'medium',
            target_question_count: 1,
            section_ids: [1],
            started_at: '2024-01-01T00:00:00Z',
            finished_at: null,
            average_score: 10,
            attempts: [
              {
                id: 1,
                question: 'Q1 text',
                category: 'technical',
                format: 'quiz',
                options: ['Right B', 'Wrong A'],
                selected_index: 0,
                correct_index: 0,
                answer: null,
                score: 10,
                feedback: 'Correct!',
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

    renderWithProviders(<SummaryScreen sessionId="s1" onDone={() => {}} />)

    await waitFor(() => expect(screen.getByText('Q1 text')).toBeInTheDocument())
    expect(screen.getByText('Your answer: Right B')).toBeInTheDocument()
    expect(screen.getByText('Correct answer: Right B')).toBeInTheDocument()
  })
})
