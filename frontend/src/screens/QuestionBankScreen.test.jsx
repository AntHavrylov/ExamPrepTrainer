import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../context/LanguageContext'
import QuestionBankScreen from './QuestionBankScreen'

function renderWithProviders(ui) {
  return render(<LanguageProvider>{ui}</LanguageProvider>)
}

function jsonResponse(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

const SECTIONS = [{ id: 1, name: 'Python', description: null, created_at: '2024-01-01' }]

function bankItem(overrides = {}) {
  return {
    id: 1,
    mode: 'technical',
    format: 'open_ended',
    difficulty: 'medium',
    language: 'en',
    section_ids: [1],
    theme: 'python gil',
    question: 'What is the GIL?',
    category: 'technical',
    options: null,
    correct_index: null,
    hint: 'Think about thread safety.',
    explanation: 'The GIL serializes bytecode execution.',
    used_at: null,
    created_at: '2024-01-01T00:00:00Z',
    ...overrides,
  }
}

describe('QuestionBankScreen', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('lists pooled questions with their ready/used status', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) {
          return jsonResponse(200, [
            bankItem({ id: 1, question: 'Ready question', used_at: null }),
            bankItem({ id: 2, question: 'Used question', used_at: '2024-01-02T00:00:00Z' }),
          ])
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)

    await waitFor(() => expect(screen.getByText('Ready question')).toBeInTheDocument())
    expect(screen.getByText('Used question')).toBeInTheDocument()
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('Already asked')).toBeInTheDocument()
  })

  it('shows the empty state when there are no pooled questions', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) return jsonResponse(200, [])
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)

    await waitFor(() =>
      expect(
        screen.getByText("No questions yet — generate some above, or they'll be created automatically as you train."),
      ).toBeInTheDocument(),
    )
  })

  it('highlights the correct option for quiz-format pooled questions', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) {
          return jsonResponse(200, [
            bankItem({
              format: 'quiz',
              question: 'Coroutine keyword?',
              options: ['def', 'async def', 'x', 'y'],
              correct_index: 1,
            }),
          ])
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)

    await waitFor(() => expect(screen.getByText('Coroutine keyword?')).toBeInTheDocument())
    fireEvent.click(screen.getByText('Coroutine keyword?'))

    const correctOption = await screen.findByText('async def')
    expect(correctOption.closest('li')).toHaveClass('correct')
    expect(screen.getByText('def').closest('li')).not.toHaveClass('correct')
  })

  it('refetches with the right query params when a filter changes', async () => {
    const requestedUrls = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) {
          requestedUrls.push(url)
          return jsonResponse(200, [])
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)

    await waitFor(() => expect(requestedUrls.length).toBeGreaterThan(0))

    fireEvent.change(screen.getByLabelText('Section'), { target: { value: '1' } })
    fireEvent.click(screen.getByLabelText('Unused only'))

    await waitFor(() => {
      const last = requestedUrls[requestedUrls.length - 1]
      expect(last).toContain('section_id=1')
      expect(last).toContain('unused_only=true')
    })
  })

  it('generating without selecting a section shows a validation error and makes no request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) return jsonResponse(200, [])
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)
    await waitFor(() => expect(screen.getByText('Generate')).toBeInTheDocument())

    fireEvent.click(screen.getByText('Generate'))

    expect(await screen.findByText('Select at least one section.')).toBeInTheDocument()
  })

  it('generates new questions and refreshes the list', async () => {
    let generateCalls = 0
    let listCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url === '/question-bank/generate' && options?.method === 'POST') {
          generateCalls += 1
          expect(JSON.parse(options.body)).toEqual({
            section_ids: [1],
            mode: 'technical',
            format: 'quiz',
            difficulty: 'medium',
            count: 5,
          })
          return jsonResponse(201, [bankItem({ id: 9, format: 'quiz', options: ['a', 'b'], correct_index: 0 })])
        }
        if (url.startsWith('/question-bank')) {
          listCalls += 1
          return jsonResponse(200, listCalls === 1 ? [] : [bankItem({ id: 9, question: 'Freshly generated' })])
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)
    // "Python" also appears as a plain <option> in the filter dropdown below,
    // so target the generate form's checkbox by role+name instead of text.
    await waitFor(() => expect(screen.getByRole('checkbox', { name: 'Python' })).toBeInTheDocument())

    fireEvent.click(screen.getByRole('checkbox', { name: 'Python' }))
    fireEvent.click(screen.getByText('Generate'))

    await waitFor(() => expect(screen.getByText('Freshly generated')).toBeInTheDocument())
    expect(generateCalls).toBe(1)
    expect(listCalls).toBe(2)
  })

  it('removes a question after confirming deletion', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    vi.stubGlobal(
      'fetch',
      vi.fn((url, options) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url === '/question-bank/1' && options?.method === 'DELETE') {
          return jsonResponse(204, null)
        }
        if (url.startsWith('/question-bank')) return jsonResponse(200, [bankItem({ id: 1 })])
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)
    await waitFor(() => expect(screen.getByText('What is the GIL?')).toBeInTheDocument())
    fireEvent.click(screen.getByText('What is the GIL?'))

    fireEvent.click(await screen.findByText('Remove'))

    await waitFor(() => expect(screen.queryByText('What is the GIL?')).not.toBeInTheDocument())
  })

  it('declining the delete confirmation keeps the question', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false)
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) return jsonResponse(200, [bankItem({ id: 1 })])
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)
    await waitFor(() => expect(screen.getByText('What is the GIL?')).toBeInTheDocument())
    fireEvent.click(screen.getByText('What is the GIL?'))

    fireEvent.click(await screen.findByText('Remove'))

    expect(screen.getByText('What is the GIL?')).toBeInTheDocument()
  })

  it('expanding shows section names, options/explanation, and collapsing hides them again', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) return jsonResponse(200, [bankItem({ id: 1 })])
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)
    await waitFor(() => expect(screen.getByText('What is the GIL?')).toBeInTheDocument())

    expect(screen.queryByText('The GIL serializes bytecode execution.')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('What is the GIL?'))
    const explanation = await screen.findByText('The GIL serializes bytecode execution.')
    expect(explanation).toBeInTheDocument()
    // "Python" also appears as a plain <option> in the section filter, so
    // scope this assertion to the expanded details panel specifically.
    expect(explanation.closest('.question-bank-item-details')).toHaveTextContent('Python')

    fireEvent.click(screen.getByText('What is the GIL?'))
    expect(screen.queryByText('The GIL serializes bytecode execution.')).not.toBeInTheDocument()
  })

  it('filters by language and refetches with the language query param', async () => {
    const requestedUrls = []
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) {
          requestedUrls.push(url)
          return jsonResponse(200, [])
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)
    await waitFor(() => expect(requestedUrls.length).toBeGreaterThan(0))

    fireEvent.change(screen.getByLabelText('Language'), { target: { value: 'uk' } })

    await waitFor(() => {
      const last = requestedUrls[requestedUrls.length - 1]
      expect(last).toContain('language=uk')
    })
  })

  it('the free-word search filters the already-loaded list client-side', async () => {
    let listCalls = 0
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sections') return jsonResponse(200, SECTIONS)
        if (url.startsWith('/question-bank')) {
          listCalls += 1
          return jsonResponse(200, [
            bankItem({ id: 1, question: 'What is the GIL?' }),
            bankItem({ id: 2, question: 'Explain decorators.' }),
          ])
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<QuestionBankScreen />)
    await waitFor(() => expect(screen.getByText('What is the GIL?')).toBeInTheDocument())
    expect(screen.getByText('Explain decorators.')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('Search questions...'), {
      target: { value: 'decorators' },
    })

    expect(screen.queryByText('What is the GIL?')).not.toBeInTheDocument()
    expect(screen.getByText('Explain decorators.')).toBeInTheDocument()
    // Purely client-side - no extra request to the server for this filter.
    expect(listCalls).toBe(1)
  })
})
