import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'

export default function StartTrainingScreen({ onStarted }) {
  const { t } = useLanguage()
  const [sections, setSections] = useState([])
  const [selectedIds, setSelectedIds] = useState([])
  const [mode, setMode] = useState('technical')
  const [format, setFormat] = useState('quiz')
  const [difficulty, setDifficulty] = useState('medium')
  const [error, setError] = useState(null)
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

  async function handleStart(e) {
    e.preventDefault()
    if (selectedIds.length === 0) {
      setError(t('startTraining.selectAtLeastOne'))
      return
    }
    setError(null)
    setStarting(true)
    try {
      const session = await api.startSession(selectedIds, mode, format, difficulty)
      onStarted(session.id)
    } catch (err) {
      setError(err.message)
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

      <form onSubmit={handleStart}>
        <div className="field-group">
          <span className="field-label">{t('startTraining.sectionsLegend')}</span>
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
