import { useEffect, useState } from 'react'
import { api } from '../api'

export default function SummaryScreen({ sessionId, onDone }) {
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    api
      .getSession(sessionId)
      .then(setSummary)
      .catch((err) => setError(err.message))
  }, [sessionId])

  if (error)
    return (
      <p className="error" role="alert">
        {error}
      </p>
    )
  if (!summary) return <p>Loading summary...</p>

  const answered = summary.attempts.filter((a) => a.score !== null)

  return (
    <div className="summary-screen">
      <h2>Session summary</h2>
      <p>
        Mode: {summary.mode} · Format: {summary.format}
      </p>
      <p>
        Average score: {summary.average_score !== null ? summary.average_score.toFixed(1) : '—'} / 10
      </p>

      <ol className="summary-list">
        {answered.map((a) => (
          <li key={a.id}>
            <p className="question">{a.question}</p>
            <p>Score: {a.score} / 10</p>
            {a.feedback && <p>{a.feedback}</p>}
          </li>
        ))}
        {answered.length === 0 && <li>No answered questions yet.</li>}
      </ol>

      <button onClick={onDone}>Back to sections</button>
    </div>
  )
}
