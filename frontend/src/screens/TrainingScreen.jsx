import { useState } from 'react'
import { api } from '../api'

export default function TrainingScreen({ sessionId, onFinish }) {
  const [question, setQuestion] = useState(null)
  const [answerText, setAnswerText] = useState('')
  const [result, setResult] = useState(null)
  const [streamingFeedback, setStreamingFeedback] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [questionCount, setQuestionCount] = useState(0)

  async function fetchNext() {
    setError(null)
    setLoading(true)
    setResult(null)
    setStreamingFeedback('')
    setAnswerText('')
    try {
      const next = await api.nextQuestion(sessionId)
      setQuestion(next)
      setQuestionCount((c) => c + 1)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitOpenEnded(e) {
    e.preventDefault()
    if (!answerText.trim()) return
    setLoading(true)
    setError(null)
    setStreamingFeedback('')
    try {
      const res = await api.streamAnswer(sessionId, answerText, (delta) =>
        setStreamingFeedback((prev) => prev + delta),
      )
      setResult(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitQuizChoice(index) {
    if (result || loading) return
    setLoading(true)
    setError(null)
    try {
      const res = await api.submitAnswer(sessionId, { selected_index: index })
      setResult(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  if (!question) {
    return (
      <div className="training-screen">
        <h2>Training</h2>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button onClick={fetchNext} disabled={loading}>
          {loading ? 'Generating question...' : 'Get first question'}
        </button>
      </div>
    )
  }

  const isQuiz = Boolean(question.options)

  return (
    <div className="training-screen">
      <h2>Question {questionCount}</h2>
      <p className="category">{question.category}</p>
      <p className="question">{question.question}</p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {!result && isQuiz && (
        <div className="quiz-options">
          {question.options.map((opt, idx) => (
            <button key={idx} onClick={() => submitQuizChoice(idx)} disabled={loading}>
              {opt}
            </button>
          ))}
        </div>
      )}

      {!result && !isQuiz && (
        <form onSubmit={submitOpenEnded}>
          <textarea
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            rows={6}
            placeholder="Type your answer..."
            disabled={loading}
          />
          <button type="submit" disabled={loading || !answerText.trim()}>
            {loading ? 'Scoring...' : 'Submit answer'}
          </button>
        </form>
      )}

      {loading && !result && isQuiz && <p>Working, this can take a few seconds...</p>}
      {loading && !result && !isQuiz && (
        <p className="streaming-feedback">{streamingFeedback || 'Working, this can take a few seconds...'}</p>
      )}

      {result && (
        <div className="result">
          {isQuiz && (
            <p className={result.is_correct ? 'correct' : 'incorrect'}>
              {result.is_correct
                ? 'Correct!'
                : `Incorrect — correct answer: ${question.options[result.correct_index]}`}
            </p>
          )}
          <p>Score: {result.score} / 10</p>
          {!isQuiz && result.feedback && <p>{result.feedback}</p>}
          {result.strengths.length > 0 && (
            <div>
              <strong>Strengths</strong>
              <ul>
                {result.strengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {result.gaps.length > 0 && (
            <div>
              <strong>Gaps</strong>
              <ul>
                {result.gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </div>
          )}

          <button onClick={fetchNext} disabled={loading}>
            Next question
          </button>
          <button onClick={onFinish} disabled={loading}>
            Finish &amp; see summary
          </button>
        </div>
      )}
    </div>
  )
}
