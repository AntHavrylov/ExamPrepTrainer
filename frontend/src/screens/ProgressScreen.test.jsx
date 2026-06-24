import { render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { LanguageProvider } from '../context/LanguageContext'
import ProgressScreen from './ProgressScreen'

function renderWithProviders(ui) {
  return render(<LanguageProvider>{ui}</LanguageProvider>)
}

function jsonResponse(status, body) {
  return Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(body) })
}

describe('ProgressScreen score history chart', () => {
  it('renders a line graph (svg path), not bars', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/stats') {
          return jsonResponse(200, {
            total_attempts: 3,
            average_score: 7,
            score_history: [
              { attempt_id: 1, created_at: '2024-01-01T00:00:00Z', score: 5 },
              { attempt_id: 2, created_at: '2024-01-02T00:00:00Z', score: 8 },
              { attempt_id: 3, created_at: '2024-01-03T00:00:00Z', score: 8 },
            ],
            weakest_topics: [],
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    const { container } = renderWithProviders(<ProgressScreen />)

    await waitFor(() => expect(screen.getByText('Score history')).toBeInTheDocument())

    expect(container.querySelector('svg.score-chart')).toBeInTheDocument()
    expect(container.querySelector('.score-chart-line')).toBeInTheDocument()
    expect(container.querySelectorAll('.score-chart-point')).toHaveLength(3)
    expect(container.querySelector('.score-bar')).not.toBeInTheDocument()
  })

  it('does not crash with a single data point', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/stats') {
          return jsonResponse(200, {
            total_attempts: 1,
            average_score: 6,
            score_history: [{ attempt_id: 1, created_at: '2024-01-01T00:00:00Z', score: 6 }],
            weakest_topics: [],
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    const { container } = renderWithProviders(<ProgressScreen />)

    await waitFor(() => expect(container.querySelectorAll('.score-chart-point')).toHaveLength(1))
    expect(screen.getByText('Not enough data yet')).toBeInTheDocument()
  })
})

describe('ProgressScreen stat cards', () => {
  it('shows average, total, latest score and trend, plus the weakest topic', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/stats') {
          return jsonResponse(200, {
            total_attempts: 6,
            average_score: 6.5,
            score_history: [
              { attempt_id: 1, created_at: '2024-01-01T00:00:00Z', score: 4 },
              { attempt_id: 2, created_at: '2024-01-02T00:00:00Z', score: 4 },
              { attempt_id: 3, created_at: '2024-01-03T00:00:00Z', score: 5 },
              { attempt_id: 4, created_at: '2024-01-04T00:00:00Z', score: 8 },
              { attempt_id: 5, created_at: '2024-01-05T00:00:00Z', score: 9 },
              { attempt_id: 6, created_at: '2024-01-06T00:00:00Z', score: 9 },
            ],
            weakest_topics: [
              { section_id: 1, section_name: 'RabbitMQ', average_score: 4.0, attempt_count: 3 },
              { section_id: 2, section_name: 'Kafka', average_score: 7.0, attempt_count: 2 },
            ],
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    const { container } = renderWithProviders(<ProgressScreen />)

    await waitFor(() => expect(screen.getByText('Average score')).toBeInTheDocument())

    const cards = [...container.querySelectorAll('.stat-card')]
    const cardByLabel = (label) => cards.find((c) => within(c).queryByText(label))

    expect(within(cardByLabel('Average score')).getByText('6.5 / 10')).toBeInTheDocument()
    expect(within(cardByLabel('Total answered')).getByText('6')).toBeInTheDocument()

    const latestCard = cardByLabel('Latest score')
    expect(within(latestCard).getByText('9 / 10')).toBeInTheDocument()
    expect(within(latestCard).getByText('↑ Improving')).toBeInTheDocument()

    const weakestCard = cardByLabel('Weakest topic')
    expect(within(weakestCard).getByText('4.0 / 10')).toBeInTheDocument()
    expect(within(weakestCard).getByText('RabbitMQ')).toBeInTheDocument()

    // Weakest-topics list itself, redesigned as ranked rows.
    const topicList = container.querySelector('.topic-list')
    expect(within(topicList).getByText('3 answers')).toBeInTheDocument()
    expect(within(topicList).getByText('Kafka')).toBeInTheDocument()
  })

  it('omits the weakest-topic card when there are no topics yet', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url) => {
        if (url === '/sessions/stats') {
          return jsonResponse(200, {
            total_attempts: 1,
            average_score: 5,
            score_history: [{ attempt_id: 1, created_at: '2024-01-01T00:00:00Z', score: 5 }],
            weakest_topics: [],
          })
        }
        throw new Error(`Unexpected fetch to ${url}`)
      }),
    )

    renderWithProviders(<ProgressScreen />)

    await waitFor(() => expect(screen.getByText('Average score')).toBeInTheDocument())
    expect(screen.queryByText('Weakest topic')).not.toBeInTheDocument()
  })
})
