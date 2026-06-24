import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'
import { OPEN_ENDED_EXPLANATION_THRESHOLD } from '../constants'

export default function TrainingScreen({ sessionId, onFinish, onInterrupt }) {
  const { t } = useLanguage()
  const [question, setQuestion] = useState(null)
  const [answerText, setAnswerText] = useState('')
  const [result, setResult] = useState(null)
  const [streamingFeedback, setStreamingFeedback] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingNext, setLoadingNext] = useState(false)
  const [error, setError] = useState(null)
  const [showHint, setShowHint] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(null)

  const isQuiz = Boolean(question?.options)

  async function fetchNext() {
    setError(null)
    setLoading(true)
    setLoadingNext(true)
    try {
      let next
      try {
        next = await api.nextQuestion(sessionId)
      } catch (err) {
        // Transient generation failures (AI rate limit/timeout) are common
        // enough to deserve one silent retry before bothering the user with
        // an error - 409 means the session is genuinely done, not transient,
        // so that one skips straight to the outer handler instead.
        if (err.status === 409) throw err
        next = await api.nextQuestion(sessionId)
      }
      // Only clear the previous question's state once the new one actually
      // arrives - clearing it beforehand meant a failed generation left the
      // old (already-answered) question on screen but looking unanswered
      // again, which read as if it had silently skipped ahead.
      setQuestion(next)
      setResult(null)
      setStreamingFeedback('')
      setAnswerText('')
      setShowHint(false)
      setSelectedIndex(null)
    } catch (err) {
      if (err.status === 409) {
        // The session was already completed or finished elsewhere (e.g. resumed
        // after the last question had already been answered) - nothing left to
        // train, so just show what's there.
        onFinish()
        return
      }
      setError(err.message)
    } finally {
      setLoading(false)
      setLoadingNext(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function resume() {
      setError(null)
      setLoading(true)
      setLoadingNext(true)
      try {
        const session = await api.getSession(sessionId)
        if (cancelled) return

        if (session.finished_at || session.attempts.length >= session.target_question_count) {
          onFinish()
          return
        }

        const last = session.attempts[session.attempts.length - 1]
        if (last && last.score === null) {
          setQuestion({
            attempt_id: last.id,
            question: last.question,
            category: last.category,
            options: last.options,
            hint: last.hint,
            question_number: session.attempts.length,
            total_questions: session.target_question_count,
          })
          setLoading(false)
          setLoadingNext(false)
          return
        }

        await fetchNext()
      } catch (err) {
        if (!cancelled) {
          setError(err.message)
          setLoading(false)
          setLoadingNext(false)
        }
      }
    }

    resume()
    return () => {
      cancelled = true
    }
    // Runs once per mounted session to either resume a pending/in-progress
    // session or kick off a brand new one.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  async function handleFinish() {
    try {
      await api.finishSession(sessionId)
    } catch {
      // Best effort - the summary screen works regardless of whether this succeeded.
    }
    onFinish()
  }

  async function handleInterrupt() {
    if (!window.confirm(t('training.interruptConfirm'))) return
    try {
      await api.finishSession(sessionId)
    } catch {
      // Best effort - the user still wants to leave.
    }
    onInterrupt()
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

      if (result && !loading && e.key === 'n' && question.question_number < question.total_questions) {
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
        <h2>{t('training.title')}</h2>
        {error ? (
          <>
            <p className="error" role="alert">
              {error}
            </p>
            <button onClick={fetchNext} disabled={loading}>
              {t('training.getFirstQuestion')}
            </button>
          </>
        ) : (
          <div className="loading-block" aria-busy="true" aria-live="polite">
            <span className="spinner" aria-hidden="true" />
            <p>{t('training.generatingQuestion')}</p>
          </div>
        )}
      </div>
    )
  }

  if (loadingNext) {
    return (
      <div className="training-screen">
        <div className="training-header">
          <h2>
            {t('training.questionNumber', {
              n: question.question_number + 1,
              total: question.total_questions,
            })}
          </h2>
          <button type="button" className="btn-danger" onClick={handleInterrupt}>
            {t('training.interrupt')}
          </button>
        </div>
        <div className="loading-block" aria-busy="true" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          <p>{t('training.generatingNext')}</p>
        </div>
      </div>
    )
  }

  const showExplanation =
    !isQuiz && result && result.score < OPEN_ENDED_EXPLANATION_THRESHOLD && result.explanation
  const atSessionLimit = question.question_number >= question.total_questions

  return (
    <div className="training-screen">
      <div className="training-header">
        <h2>
          {t('training.questionNumber', { n: question.question_number, total: question.total_questions })}
        </h2>
        <button type="button" className="btn-danger" onClick={handleInterrupt}>
          {t('training.interrupt')}
        </button>
      </div>
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
            <p className="hint">{t('training.hint', { text: question.hint })}</p>
          ) : (
            <button type="button" className="btn-secondary" onClick={() => setShowHint(true)}>
              {t('training.showHint')} <span className="shortcut-tag">h</span>
            </button>
          )}
        </div>
      )}

      {isQuiz && (
        <div className="quiz-options">
          {question.options.map((opt, idx) => {
            const variant = result && idx === selectedIndex ? (result.is_correct ? 'correct' : 'incorrect') : ''
            return (
              <button
                key={idx}
                className={variant}
                onClick={() => submitQuizChoice(idx)}
                disabled={Boolean(result) || loading}
              >
                <span className="shortcut-tag">{idx + 1}</span> {opt}
              </button>
            )
          })}
        </div>
      )}

      {!result && !isQuiz && (
        <form onSubmit={handleOpenEndedSubmit}>
          <textarea
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            rows={6}
            placeholder={t('training.answerPlaceholder')}
            disabled={loading}
          />
          <button type="submit" disabled={loading || !answerText.trim()}>
            {loading ? t('training.scoring') : t('training.submitAnswer')}
          </button>
        </form>
      )}

      {loading && !result && isQuiz && (
        <p className="loading-inline">
          <span className="spinner" aria-hidden="true" /> {t('training.working')}
        </p>
      )}
      {loading && !result && !isQuiz && (
        <p className="streaming-feedback">
          {streamingFeedback || (
            <span className="loading-inline">
              <span className="spinner" aria-hidden="true" /> {t('training.working')}
            </span>
          )}
        </p>
      )}

      {result && (
        <div className="result">
          {isQuiz && (
            <p className={result.is_correct ? 'correct' : 'incorrect'}>
              {result.is_correct ? t('training.correct') : t('training.incorrect')}
            </p>
          )}
          {isQuiz && !result.is_correct && (
            <div className="correct-answer-box">
              <p>{t('training.correctAnswer', { answer: question.options[result.correct_index] })}</p>
              {result.explanation && <p>{result.explanation}</p>}
            </div>
          )}
          <p>{t('training.score', { score: result.score })}</p>
          {!isQuiz && <p className="submitted-answer">{t('training.yourAnswer', { answer: answerText })}</p>}
          {!isQuiz && result.feedback && <p>{result.feedback}</p>}
          {result.strengths.length > 0 && (
            <div>
              <strong>{t('training.strengths')}</strong>
              <ul>
                {result.strengths.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            </div>
          )}
          {result.gaps.length > 0 && (
            <div>
              <strong>{t('training.gaps')}</strong>
              <ul>
                {result.gaps.map((g, i) => (
                  <li key={i}>{g}</li>
                ))}
              </ul>
            </div>
          )}
          {showExplanation && (
            <p className="explanation">{t('training.explanation', { text: result.explanation })}</p>
          )}

          {!atSessionLimit && (
            <button onClick={fetchNext} disabled={loading}>
              {t('training.nextQuestion')} <span className="shortcut-tag">n</span>
            </button>
          )}
          <button className="btn-secondary" onClick={handleFinish} disabled={loading}>
            {t('training.finish')}
          </button>
        </div>
      )}
    </div>
  )
}
