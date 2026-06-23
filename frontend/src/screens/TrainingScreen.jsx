import { useEffect, useState } from 'react'
import { api } from '../api'
import { OPEN_ENDED_EXPLANATION_THRESHOLD } from '../constants'

export default function TrainingScreen({ sessionId, onFinish }) {
  const [question, setQuestion] = useState(null)
  const [answerText, setAnswerText] = useState('')
  const [result, setResult] = useState(null)
  const [streamingFeedback, setStreamingFeedback] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [questionCount, setQuestionCount] = useState(0)
  const [showHint, setShowHint] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(null)

  const isQuiz = Boolean(question?.options)

  async function fetchNext() {
    setError(null)
    setLoading(true)
    setResult(null)
    setStreamingFeedback('')
    setAnswerText('')
    setShowHint(false)
    setSelectedIndex(null)
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

  async function submitOpenEnded() {
    if (!answerText.trim() || loading) return
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

  function handleOpenEndedSubmit(e) {
    e.preventDefault()
    submitOpenEnded()
  }

  async function submitQuizChoice(index) {
    if (result || loading) return
    setLoading(true)
    setError(null)
    setSelectedIndex(index)
    try {
      const res = await api.submitAnswer(sessionId, { selected_index: index })
      setResult(res)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    function handleKeyDown(e) {
      const activeTag = document.activeElement?.tagName
      const isTyping = activeTag === 'TEXTAREA' || activeTag === 'INPUT'

      if (!question) return

      if (!result && isQuiz && !loading && !isTyping && /^[1-4]$/.test(e.key)) {
        const idx = Number(e.key) - 1
        if (idx < question.options.length) submitQuizChoice(idx)
        return
      }

      if (!result && !isQuiz && (e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault()
        submitOpenEnded()
        return
      }

      if (!result && !loading && !isTyping && e.key === 'h') {
        setShowHint((prev) => !prev)
        return
      }

      if (result && !loading && e.key === 'n') {
        fetchNext()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // fetchNext/submitOpenEnded/submitQuizChoice only close over values already listed
    // below; listing the functions too would just re-run this effect on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question, result, loading, isQuiz, answerText])

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

  const showExplanation = isQuiz
    ? result && !result.is_correct && result.explanation
    : result && result.score < OPEN_ENDED_EXPLANATION_THRESHOLD && result.explanation

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

      {!result && question.hint && (
        <div className="hint-block">
          {showHint ? (
            <p className="hint">Hint: {question.hint}</p>
          ) : (
            <button type="button" className="btn-secondary" onClick={() => setShowHint(true)}>
              Show hint <span className="shortcut-tag">h</span>
            </button>
          )}
        </div>
      )}

      {!result && isQuiz && (
        <div className="quiz-options">
          {question.options.map((opt, idx) => (
            <button key={idx} onClick={() => submitQuizChoice(idx)} disabled={loading}>
              <span className="shortcut-tag">{idx + 1}</span> {opt}
            </button>
          ))}
        </div>
      )}

      {!result && !isQuiz && (
        <form onSubmit={handleOpenEndedSubmit}>
          <textarea
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            rows={6}
            placeholder="Type your answer... (Ctrl+Enter to submit)"
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
              {result.is_correct ? 'Correct!' : 'Incorrect'}
            </p>
          )}
          {isQuiz && !result.is_correct && (
            <>
              <p className="submitted-answer">Your answer: {question.options[selectedIndex]}</p>
              <p>Correct answer: {question.options[result.correct_index]}</p>
            </>
          )}
          <p>Score: {result.score} / 10</p>
          {!isQuiz && <p className="submitted-answer">Your answer: {answerText}</p>}
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
          {showExplanation && <p className="explanation">Explanation: {result.explanation}</p>}

          <button onClick={fetchNext} disabled={loading}>
            Next question <span className="shortcut-tag">n</span>
          </button>
          <button className="btn-secondary" onClick={onFinish} disabled={loading}>
            Finish &amp; see summary
          </button>
        </div>
      )}
    </div>
  )
}
