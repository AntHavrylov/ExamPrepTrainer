import { useEffect, useState } from 'react'
import { api } from '../api'
import { OPEN_ENDED_EXPLANATION_THRESHOLD } from '../constants'

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
  const isQuiz = summary.format === 'quiz'

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
        {answered.map((a) => {
          const wrongQuiz = isQuiz && a.selected_index !== a.correct_index
          const lowOpenEnded = !isQuiz && a.score < OPEN_ENDED_EXPLANATION_THRESHOLD
          const showExplanation = (wrongQuiz || lowOpenEnded) && a.explanation
          return (
            <li key={a.id}>
              <p className="question">{a.question}</p>
              {isQuiz && a.options && (
                <p className={wrongQuiz ? 'incorrect' : 'correct'}>{wrongQuiz ? 'Incorrect' : 'Correct!'}</p>
              )}
              {isQuiz && a.options && wrongQuiz && (
                <>
                  <p className="submitted-answer">Your answer: {a.options[a.selected_index]}</p>
                  <p>Correct answer: {a.options[a.correct_index]}</p>
                </>
              )}
              <p>Score: {a.score} / 10</p>
              {!isQuiz && a.answer && <p className="submitted-answer">Your answer: {a.answer}</p>}
              {a.feedback && <p>{a.feedback}</p>}
              {showExplanation && <p className="explanation">Explanation: {a.explanation}</p>}
            </li>
          )
        })}
        {answered.length === 0 && <li>No answered questions yet.</li>}
      </ol>

      <button onClick={onDone}>Back to sections</button>
    </div>
  )
}
