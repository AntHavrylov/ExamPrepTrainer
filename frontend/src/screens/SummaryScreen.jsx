import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'

const MODE_KEYS = {
  technical: 'enums.modeTechnical',
  behavioral: 'enums.modeBehavioral',
  mixed: 'enums.modeMixed',
}

const FORMAT_KEYS = {
  open_ended: 'enums.formatOpenEnded',
  quiz: 'enums.formatQuiz',
}

export default function SummaryScreen({ sessionId, onDone, onTrainAgain }) {
  const { t } = useLanguage()
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
  if (!summary) return <p>{t('summary.loading')}</p>

  const answered = summary.attempts.filter((a) => a.score !== null)
  const isQuiz = summary.format === 'quiz'

  return (
    <div className="summary-screen">
      <h2>{t('summary.title')}</h2>
      <div className="session-summary-card">
        <p>
          {t('summary.modeFormat', {
            mode: t(MODE_KEYS[summary.mode] || summary.mode),
            format: t(FORMAT_KEYS[summary.format] || summary.format),
          })}
        </p>
        <p className="session-summary-score">
          {t('summary.average', {
            score: summary.average_score !== null ? summary.average_score.toFixed(1) : '—',
          })}
        </p>
      </div>

      <ol className="summary-list">
        {answered.map((a) => {
          const wrongQuiz = isQuiz && a.selected_index !== a.correct_index
          const showExplanation = a.explanation
          return (
            <li key={a.id}>
              <p className="question">{a.question}</p>
              {isQuiz && a.options && (
                <p className={wrongQuiz ? 'incorrect' : 'correct'}>
                  {wrongQuiz ? t('summary.incorrect') : t('summary.correct')}
                </p>
              )}
              {isQuiz && a.options && (
                <>
                  <p className="submitted-answer">
                    {t('summary.yourAnswer', { answer: a.options[a.selected_index] })}
                  </p>
                  <p>{t('summary.correctAnswer', { answer: a.options[a.correct_index] })}</p>
                </>
              )}
              <p>{t('summary.score', { score: a.score })}</p>
              {!isQuiz && a.answer && (
                <p className="submitted-answer">{t('summary.yourAnswer', { answer: a.answer })}</p>
              )}
              {a.feedback && <p>{a.feedback}</p>}
              {showExplanation && (
                <p className="explanation">{t('summary.explanation', { text: a.explanation })}</p>
              )}
            </li>
          )
        })}
        {answered.length === 0 && <li>{t('summary.none')}</li>}
      </ol>

      <div className="summary-actions">
        {onTrainAgain && (
          <button
            className="btn-secondary"
            onClick={() =>
              onTrainAgain({
                selectedIds: summary.section_ids,
                mode: summary.mode,
                format: summary.format,
                difficulty: summary.difficulty,
              })
            }
          >
            {t('summary.trainAgain')}
          </button>
        )}
        <button onClick={onDone}>{t('summary.back')}</button>
      </div>
    </div>
  )
}
