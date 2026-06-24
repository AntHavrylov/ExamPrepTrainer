import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../context/LanguageContext'
import TrainingScreen from './TrainingScreen'

function renderWithProviders(ui) {
  return render(<LanguageProvider>{ui}</LanguageProvider>)
}

function jsonResponse(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

function errorResponse(status, detail) {
  return Promise.resolve({ ok: false, status, json: () => Promise.resolve({ detail }) })
}

function deferred() {
  let resolve
  const promise = new Promise((res) => {
    resolve = res
  })
  return { promise, resolve }
}

function freshSession(overrides = {}) {
  return {
    id: 1,
    mode: 'technical',
    format: 'quiz',
    difficulty: 'medium',
    target_question_count: 5,
    section_ids: [1],
    started_at: '2024-01-01T00:00:00Z',
    finished_at: null,
    attempts: [],
    ...overrides,
  }
}

describe('TrainingScreen quiz flow', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('keeps the answer options visible and colors the chosen one after answering', async () => {
    const question = {
      question: 'Q1 text',
      category: 'technical',
      options: ['Wrong A', 'Right B', 'Wrong C', 'Wrong D'],
      question_number: 1,
      total_questions: 5,
    }
    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/sessions/s1') return jsonResponse(200, freshSession())
        if (url === '/sessions/s1/next') return jsonResponse(200, question)
        if (url === '/sessions/s1/answer' && options?.method === 'POST') {
          return jsonResponse(200, {
            score: 0,
            feedback: '',
            strengths: [],
            gaps: [],
            correct_index: 1,
            is_correct: false,
            explanation: 'B is right because of reasons.',
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={() => {}} onInterrupt={() => {}} />)

    await waitFor(() => expect(screen.getByText('Q1 text')).toBeInTheDocument())
    expect(screen.getByText('Question 1 / 5')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Wrong A'))

    await waitFor(() => expect(screen.getByText('Incorrect')).toBeInTheDocument())

    // The question and all of its options must still be visible.
    expect(screen.getByText('Q1 text')).toBeInTheDocument()
    expect(screen.getByText('Wrong A')).toBeInTheDocument()
    expect(screen.getByText('Right B')).toBeInTheDocument()

    const chosenButton = screen.getByText('Wrong A').closest('button')
    expect(chosenButton).toHaveClass('incorrect')
    expect(chosenButton).toBeDisabled()

    const box = screen.getByText('Correct answer: Right B').closest('.correct-answer-box')
    expect(box).toHaveTextContent('B is right because of reasons.')
  })

  it('keeps the just-answered question and its result on screen if generating the next one fails', async () => {
    const question = {
      question: 'Q1 text',
      category: 'technical',
      options: ['Wrong A', 'Right B'],
      question_number: 1,
      total_questions: 5,
    }
    let nextCallCount = 0

    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/sessions/s1') return jsonResponse(200, freshSession())
        if (url === '/sessions/s1/next') {
          nextCallCount += 1
          if (nextCallCount === 1) return jsonResponse(200, question)
          return errorResponse(503, 'OpenRouter returned 503')
        }
        if (url === '/sessions/s1/answer' && options?.method === 'POST') {
          return jsonResponse(200, {
            score: 0,
            feedback: '',
            strengths: [],
            gaps: [],
            correct_index: 1,
            is_correct: false,
            explanation: null,
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={() => {}} onInterrupt={() => {}} />)

    await waitFor(() => expect(screen.getByText('Q1 text')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Wrong A'))
    await waitFor(() => expect(screen.getByText('Incorrect')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Next question'))

    await waitFor(() => expect(screen.getByText('OpenRouter returned 503')).toBeInTheDocument())

    // Must still show the answered question's result, not reset it to looking
    // unanswered (which previously happened because state was cleared before
    // the request resolved).
    expect(screen.getByText('Q1 text')).toBeInTheDocument()
    expect(screen.getByText('Incorrect')).toBeInTheDocument()
    const chosenButton = screen.getByText('Wrong A').closest('button')
    expect(chosenButton).toHaveClass('incorrect')
  })

  it('silently retries once on a transient /next failure before showing an error', async () => {
    const question1 = {
      question: 'Q1 text',
      category: 'technical',
      options: ['A', 'B'],
      question_number: 1,
      total_questions: 5,
    }
    const question2 = {
      question: 'Q2 text',
      category: 'technical',
      options: ['C', 'D'],
      question_number: 2,
      total_questions: 5,
    }
    let nextCallCount = 0

    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/sessions/s1') return jsonResponse(200, freshSession())
        if (url === '/sessions/s1/next') {
          nextCallCount += 1
          if (nextCallCount === 1) return jsonResponse(200, question1)
          if (nextCallCount === 2) return errorResponse(503, 'OpenRouter returned 503')
          return jsonResponse(200, question2)
        }
        if (url === '/sessions/s1/answer' && options?.method === 'POST') {
          return jsonResponse(200, {
            score: 10,
            feedback: '',
            strengths: [],
            gaps: [],
            correct_index: 0,
            is_correct: true,
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={() => {}} onInterrupt={() => {}} />)

    await waitFor(() => expect(screen.getByText('Q1 text')).toBeInTheDocument())
    fireEvent.click(screen.getByText('A'))
    await waitFor(() => expect(screen.getByText('Correct!')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Next question'))

    // The first /next attempt failed, but the silent retry succeeded - the
    // new question should appear directly, with no error ever shown.
    await waitFor(() => expect(screen.getByText('Q2 text')).toBeInTheDocument())
    expect(screen.queryByText('OpenRouter returned 503')).not.toBeInTheDocument()
    expect(nextCallCount).toBe(3)
  })

  it('shows a dedicated loading view instead of the stale question while fetching the next one', async () => {
    const question1 = {
      question: 'Q1 text',
      category: 'technical',
      options: ['A', 'B'],
      question_number: 1,
      total_questions: 2,
    }
    const question2 = {
      question: 'Q2 text',
      category: 'technical',
      options: ['C', 'D'],
      question_number: 2,
      total_questions: 2,
    }
    const nextDeferred = deferred()
    let nextCallCount = 0

    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/sessions/s1') return jsonResponse(200, freshSession({ target_question_count: 2 }))
        if (url === '/sessions/s1/next') {
          nextCallCount += 1
          if (nextCallCount === 1) return jsonResponse(200, question1)
          return nextDeferred.promise.then(() => jsonResponse(200, question2)).then((r) => r)
        }
        if (url === '/sessions/s1/answer' && options?.method === 'POST') {
          return jsonResponse(200, {
            score: 10,
            feedback: '',
            strengths: [],
            gaps: [],
            correct_index: 0,
            is_correct: true,
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={() => {}} onInterrupt={() => {}} />)

    await waitFor(() => expect(screen.getByText('Q1 text')).toBeInTheDocument())

    fireEvent.click(screen.getByText('A'))
    await waitFor(() => expect(screen.getByText('Correct!')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Next question'))

    // While the next question is in flight, the old one must be gone and a
    // clear loading view shown instead (not stacked on top of stale content).
    await waitFor(() => expect(screen.getByText('Generating your next question...')).toBeInTheDocument())
    expect(screen.queryByText('Q1 text')).not.toBeInTheDocument()
    expect(screen.queryByText('Correct!')).not.toBeInTheDocument()

    nextDeferred.resolve()
    await waitFor(() => expect(screen.getByText('Q2 text')).toBeInTheDocument())
    expect(screen.getByText('Question 2 / 2')).toBeInTheDocument()

    fireEvent.click(screen.getByText('C'))
    await waitFor(() => expect(screen.getByText('Correct!')).toBeInTheDocument())

    // Reached the session's configured question count: no more "Next question".
    expect(screen.queryByText('Next question')).not.toBeInTheDocument()
    expect(screen.getByText('Finish & see summary')).toBeInTheDocument()
  })

  it('resumes a pending unanswered question on mount without calling /next', async () => {
    const nextSpy = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/s1') {
          return jsonResponse(
            200,
            freshSession({
              attempts: [
                {
                  id: 7,
                  question: 'Resumed question text',
                  category: 'technical',
                  format: 'quiz',
                  options: ['X', 'Y'],
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
            }),
          )
        }
        if (url === '/sessions/s1/next') {
          nextSpy()
          return jsonResponse(200, {})
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={() => {}} onInterrupt={() => {}} />)

    await waitFor(() => expect(screen.getByText('Resumed question text')).toBeInTheDocument())
    expect(screen.getByText('Question 1 / 5')).toBeInTheDocument()
    expect(nextSpy).not.toHaveBeenCalled()
  })

  it('redirects to the summary when resuming a session that is already finished', async () => {
    const onFinish = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/s1') {
          return jsonResponse(200, freshSession({ finished_at: '2024-01-02T00:00:00Z' }))
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={onFinish} onInterrupt={() => {}} />)

    await waitFor(() => expect(onFinish).toHaveBeenCalledTimes(1))
  })

  it('redirects to the summary when /next reports the session is already complete (409)', async () => {
    const onFinish = vi.fn()
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/s1') return jsonResponse(200, freshSession())
        if (url === '/sessions/s1/next') return errorResponse(409, 'Session already has the configured number of questions')
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={onFinish} onInterrupt={() => {}} />)

    await waitFor(() => expect(onFinish).toHaveBeenCalledTimes(1))
  })

  it('Interrupt confirms, calls finishSession, and navigates away', async () => {
    const onInterrupt = vi.fn()
    const finishSpy = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/sessions/s1') return jsonResponse(200, freshSession())
        if (url === '/sessions/s1/next') {
          return jsonResponse(200, {
            question: 'Q1 text',
            category: 'technical',
            options: ['A', 'B'],
            question_number: 1,
            total_questions: 5,
          })
        }
        if (url === '/sessions/s1/finish' && options?.method === 'POST') {
          finishSpy()
          return jsonResponse(200, freshSession({ finished_at: '2024-01-02T00:00:00Z' }))
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={() => {}} onInterrupt={onInterrupt} />)

    await waitFor(() => expect(screen.getByText('Q1 text')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Interrupt'))

    await waitFor(() => expect(onInterrupt).toHaveBeenCalledTimes(1))
    expect(finishSpy).toHaveBeenCalledTimes(1)
  })

  it('declining the Interrupt confirmation does not navigate away', async () => {
    const onInterrupt = vi.fn()
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/s1') return jsonResponse(200, freshSession())
        if (url === '/sessions/s1/next') {
          return jsonResponse(200, {
            question: 'Q1 text',
            category: 'technical',
            options: ['A', 'B'],
            question_number: 1,
            total_questions: 5,
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<TrainingScreen sessionId="s1" onFinish={() => {}} onInterrupt={onInterrupt} />)

    await waitFor(() => expect(screen.getByText('Q1 text')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Interrupt'))

    expect(onInterrupt).not.toHaveBeenCalled()
  })
})
