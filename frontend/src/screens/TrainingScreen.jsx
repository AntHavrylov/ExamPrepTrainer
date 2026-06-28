import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'

const LETTERS = ['A', 'B', 'C', 'D']

function fisherYatesShuffle(n) {
  const indices = Array.from({ length: n }, (_, i) => i)
  for (let i = n - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[indices[i], indices[j]] = [indices[j], indices[i]]
  }
  return indices
}

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
  // shuffleMap[shuffledIdx] = originalIdx; null for open-ended questions
  const [shuffleMap, setShuffleMap] = useState(null)

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
        if (err.status === 409) throw err
        next = await api.nextQuestion(sessionId)
      }
      setQuestion(next)
      setResult(null)
      setStreamingFeedback('')
      setAnswerText('')
      setShowHint(false)
      setSelectedIndex(null)
    } catch (err) {
      if (err.status === 409) {
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
            section_names: last.section_names ?? [],
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
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId])

  async function handleFinish() {
    try {
      await api.finishSession(sessionId)
    } catch {
      // best effort
    }
    onFinish()
  }

  async function handleInterrupt() {
    if (!window.confirm(t('training.interruptConfirm'))) return
    try {
      await api.finishSession(sessionId)
    } catch {
      // best effort
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
        const shuffledIdx = Number(e.key) - 1
        if (shuffledIdx < question.options.length) {
          submitQuizChoice(shuffleMap ? shuffleMap[shuffledIdx] : shuffledIdx)
        }
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [question, result, loading, isQuiz, answerText, shuffleMap])

  useEffect(() => {
    if (!question?.options?.length) { setShuffleMap(null); return }
    setShuffleMap(fisherYatesShuffle(question.options.length))
  }, [question?.attempt_id])

  const progressPct = question
    ? Math.round((question.question_number / question.total_questions) * 100)
    : 0
  const atSessionLimit = question && question.question_number >= question.total_questions

  function TopBar({ showInterrupt = true }) {
    return (
      <div className="training-top-bar">
        <div className="training-progress-wrap">
          <div className="training-progress-fill" style={{ width: `${progressPct}%` }} />
        </div>
        <span className="training-counter">
          {question ? `${question.question_number} / ${question.total_questions}` : '…'}
        </span>
        {showInterrupt && (
          <button type="button" className="training-interrupt" onClick={handleInterrupt}>
            {t('training.interrupt')}
          </button>
        )}
      </div>
    )
  }

  if (!question) {
    return (
      <div className="training-screen">
        <TopBar showInterrupt />
        {error ? (
          <>
            <p className="error" role="alert">{error}</p>
            <button onClick={fetchNext} disabled={loading}>{t('training.getFirstQuestion')}</button>
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
        <TopBar showInterrupt />
        <div className="loading-block" aria-busy="true" aria-live="polite">
          <span className="spinner" aria-hidden="true" />
          <p>{t('training.generatingNext')}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="training-screen">
      <TopBar showInterrupt />

      <div className="question-card">
        <div className="question-card-meta">
          {question.section_names?.length > 0 && (
            <span className="section-pill">{question.section_names.join(' · ')}</span>
          )}
          {question.category && (
            <span className="category-pill">{question.category}</span>
          )}
        </div>

        <p className="question">{question.question}</p>

        {isQuiz && (
          <div className="quiz-options">
            {(shuffleMap ?? question.options.map((_, i) => i)).map((origIdx, shuffledIdx) => {
              const opt = question.options[origIdx]
              let variant = ''
              if (result) {
                if (origIdx === result.correct_index) variant = ' correct'
                else if (origIdx === selectedIndex) variant = ' incorrect'
                else variant = ' dimmed'
              } else if (origIdx === selectedIndex && loading) {
                variant = ' selected'
              }
              return (
                <button
                  key={shuffledIdx}
                  className={`quiz-option-btn${variant}`}
                  onClick={() => submitQuizChoice(origIdx)}
                  disabled={Boolean(result) || loading}
                >
                  <span className="quiz-option-badge">{LETTERS[shuffledIdx] || shuffledIdx + 1}</span>
                  {opt}
                </button>
              )
            })}
          </div>
        )}

        {!isQuiz && !result && (
          <form className="answer-form" onSubmit={handleOpenEndedSubmit}>
            <textarea
              value={answerText}
              onChange={(e) => setAnswerText(e.target.value)}
              rows={6}
              placeholder={t('training.answerPlaceholder')}
              disabled={loading}
            />
          </form>
        )}
      </div>

      {showHint && question.hint && (
        <div className="hint-block" role="note">
          {t('training.hint', { text: question.hint })}
        </div>
      )}

      {loading && !result && !isQuiz && (
        <div className="streaming-feedback">
          {streamingFeedback || (
            <span className="loading-inline">
              <span className="spinner" aria-hidden="true" /> {t('training.working')}
            </span>
          )}
        </div>
      )}

      {loading && !result && isQuiz && (
        <p className="loading-inline">
          <span className="spinner" aria-hidden="true" /> {t('training.working')}
        </p>
      )}

      {result && (
        <div className="verdict-block" role="status" aria-live="polite">
          {isQuiz && (
            <div className="verdict-header">
              <span className={`verdict-dot ${result.is_correct ? 'correct' : 'incorrect'}`}>
                {result.is_correct ? '✓' : '✕'}
              </span>
              <span className={`verdict-label ${result.is_correct ? 'correct' : 'incorrect'}`}>
                {result.is_correct ? t('training.correct') : t('training.incorrect')}
              </span>
              <span style={{ marginLeft: 'auto', fontSize: '13px', color: 'var(--text-3)' }}>
                {t('training.score', { score: result.score })}
              </span>
            </div>
          )}

          {isQuiz && !result.is_correct && (
            <div className="correct-answer-box">
              {t('training.correctAnswer', { answer: question.options[result.correct_index] })}
            </div>
          )}

          {result.explanation && (
            <p className="explanation">{t('training.explanation', { text: result.explanation })}</p>
          )}

          {!isQuiz && (
            <>
              <p>{t('training.score', { score: result.score })}</p>
              <p className="submitted-answer">{t('training.yourAnswer', { answer: answerText })}</p>
              {result.feedback && <p>{result.feedback}</p>}
            </>
          )}

          {result.strengths?.length > 0 && (
            <div>
              <strong>{t('training.strengths')}</strong>
              <ul>{result.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
            </div>
          )}

          {result.gaps?.length > 0 && (
            <div>
              <strong>{t('training.gaps')}</strong>
              <ul>{result.gaps.map((g, i) => <li key={i}>{g}</li>)}</ul>
            </div>
          )}
        </div>
      )}

      {error && (
        <p className="error" role="alert">{error}</p>
      )}

      <div className="action-bar">
        {!result && question.hint && (
          <button
            type="button"
            className="action-bar-hint"
            onClick={() => setShowHint((h) => !h)}
          >
            {showHint ? t('training.hideHint') : t('training.showHint')}
            <span className="action-key-badge">h</span>
          </button>
        )}

        {result ? (
          <>
            {!atSessionLimit && (
              <button
                type="button"
                className="action-bar-primary"
                onClick={fetchNext}
                disabled={loading}
              >
                {t('training.nextQuestion')}
                <span className="action-key-badge">n</span>
              </button>
            )}
            <button
              type="button"
              className="action-bar-skip"
              onClick={handleFinish}
              disabled={loading}
            >
              {t('training.finish')}
            </button>
          </>
        ) : (
          !isQuiz && (
            <button
              type="button"
              className="action-bar-primary"
              onClick={submitOpenEnded}
              disabled={loading || !answerText.trim()}
            >
              {loading ? t('training.scoring') : t('training.submitAnswer')}
              {!loading && <span className="action-key-badge">⌘↵</span>}
            </button>
          )
        )}
      </div>
    </div>
  )
}
