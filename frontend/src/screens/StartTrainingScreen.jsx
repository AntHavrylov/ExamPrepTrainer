import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'
import { LANGUAGE_NATIVE_NAMES } from '../i18n/translations'

const MODE_KEYS = {
  technical: 'enums.modeTechnical',
  behavioral: 'enums.modeBehavioral',
  mixed: 'enums.modeMixed',
}

const FORMAT_KEYS = {
  open_ended: 'enums.formatOpenEnded',
  quiz: 'enums.formatQuiz',
}

const DIFFICULTY_KEYS = {
  easy: 'enums.difficultyEasy',
  medium: 'enums.difficultyMedium',
  hard: 'enums.difficultyHard',
}

const SETTINGS_KEY = 'lastTrainingSettings'

function loadSavedSettings() {
  try {
    const raw = localStorage.getItem(SETTINGS_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

export default function StartTrainingScreen({ onStarted, onNavigate }) {
  const { t } = useLanguage()
  const [sections, setSections] = useState([])
  const saved = loadSavedSettings()
  const [selectedIds, setSelectedIds] = useState(saved?.selectedIds ?? [])
  const [mode, setMode] = useState(saved?.mode ?? 'technical')
  const [format, setFormat] = useState(saved?.format ?? 'quiz')
  const [difficulty, setDifficulty] = useState(saved?.difficulty ?? 'medium')
  const [error, setError] = useState(null)
  // Set when the backend rejects the start because no unused questions match
  // the chosen combination (incl. the active language) - carries the exact
  // failing parameters so we can show them and point the user at generation.
  const [noQuestions, setNoQuestions] = useState(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    api
      .listSections()
      .then(setSections)
      .catch((err) => setError(err.message))
  }, [])

  function toggleSection(id) {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  function toggleSelectAll() {
    setSelectedIds((prev) =>
      prev.length === sections.length ? [] : sections.map((s) => s.id),
    )
  }

  async function handleStart(e) {
    e.preventDefault()
    if (selectedIds.length === 0) {
      setError(t('startTraining.selectAtLeastOne'))
      return
    }
    setError(null)
    setNoQuestions(null)
    setStarting(true)
    localStorage.setItem(SETTINGS_KEY, JSON.stringify({ selectedIds, mode, format, difficulty }))
    try {
      const session = await api.startSession(selectedIds, mode, format, difficulty)
      onStarted(session.id)
    } catch (err) {
      if (err.status === 409 && err.detail?.code === 'no_questions') {
        setNoQuestions(err.detail)
      } else {
        setError(err.message)
      }
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="start-training-screen">
      <h2>{t('startTraining.title')}</h2>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {noQuestions && (
        <div className="no-questions-notice" role="alert">
          <h3>{t('startTraining.noQuestionsTitle')}</h3>
          <p>{t('startTraining.noQuestionsBody')}</p>
          <dl className="no-questions-params">
            <div>
              <dt>{t('startTraining.mode')}</dt>
              <dd>{t(MODE_KEYS[noQuestions.mode] || noQuestions.mode)}</dd>
            </div>
            <div>
              <dt>{t('startTraining.format')}</dt>
              <dd>{t(FORMAT_KEYS[noQuestions.format] || noQuestions.format)}</dd>
            </div>
            <div>
              <dt>{t('startTraining.difficulty')}</dt>
              <dd>{t(DIFFICULTY_KEYS[noQuestions.difficulty] || noQuestions.difficulty)}</dd>
            </div>
            <div>
              <dt>{t('startTraining.language')}</dt>
              <dd>{LANGUAGE_NATIVE_NAMES[noQuestions.language] || noQuestions.language}</dd>
            </div>
          </dl>
          <button type="button" onClick={() => onNavigate?.('question-bank')}>
            {t('startTraining.goToQuestionBank')}
          </button>
        </div>
      )}

      <form onSubmit={handleStart}>
        <div className="field-group">
          <div className="field-label-row">
            <span className="field-label">{t('startTraining.sectionsLegend')}</span>
            {sections.length > 1 && (
              <button type="button" className="btn-link" onClick={toggleSelectAll}>
                {selectedIds.length === sections.length
                  ? t('startTraining.deselectAll')
                  : t('startTraining.selectAll')}
              </button>
            )}
          </div>
          <div className="section-toggle-list">
            {sections.map((s) => {
              const checked = selectedIds.includes(s.id)
              return (
                <label key={s.id} className={`section-toggle${checked ? ' checked' : ''}`}>
                  <input type="checkbox" checked={checked} onChange={() => toggleSection(s.id)} />
                  <span>{s.name}</span>
                </label>
              )
            })}
            {sections.length === 0 && <p>{t('startTraining.noSections')}</p>}
          </div>
        </div>

        <label>
          {t('startTraining.mode')}
          <select value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="technical">{t('enums.modeTechnical')}</option>
            <option value="behavioral">{t('enums.modeBehavioral')}</option>
            <option value="mixed">{t('enums.modeMixed')}</option>
          </select>
        </label>

        <label>
          {t('startTraining.format')}
          <select value={format} onChange={(e) => setFormat(e.target.value)}>
            <option value="open_ended">{t('enums.formatOpenEnded')}</option>
            <option value="quiz">{t('enums.formatQuiz')}</option>
          </select>
        </label>

        <label>
          {t('startTraining.difficulty')}
          <select value={difficulty} onChange={(e) => setDifficulty(e.target.value)}>
            <option value="easy">{t('enums.difficultyEasy')}</option>
            <option value="medium">{t('enums.difficultyMedium')}</option>
            <option value="hard">{t('enums.difficultyHard')}</option>
          </select>
        </label>

        <button type="submit" disabled={starting}>
          {starting ? t('startTraining.starting') : t('startTraining.startBtn')}
        </button>
      </form>
    </div>
  )
}
