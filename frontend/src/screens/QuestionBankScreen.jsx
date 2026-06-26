import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'
import { LANGUAGE_NATIVE_NAMES, SUPPORTED_LANGUAGES } from '../i18n/translations'

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

export default function QuestionBankScreen() {
  const { t } = useLanguage()
  const [sections, setSections] = useState([])
  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [filterSectionId, setFilterSectionId] = useState('')
  const [filterMode, setFilterMode] = useState('')
  const [filterFormat, setFilterFormat] = useState('')
  const [filterDifficulty, setFilterDifficulty] = useState('')
  const [filterLanguage, setFilterLanguage] = useState('')
  const [unusedOnly, setUnusedOnly] = useState(false)
  const [searchText, setSearchText] = useState('')

  const [genSectionIds, setGenSectionIds] = useState([])
  const [genMode, setGenMode] = useState('technical')
  const [genFormat, setGenFormat] = useState('quiz')
  const [genDifficulty, setGenDifficulty] = useState('medium')
  const [genCount, setGenCount] = useState(5)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState(null)

  const [deletingId, setDeletingId] = useState(null)
  const [reloadToken, setReloadToken] = useState(0)
  const [expandedIds, setExpandedIds] = useState(() => new Set())

  useEffect(() => {
    api
      .listSections()
      .then(setSections)
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    let cancelled = false

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const data = await api.listQuestionBank({
          section_id: filterSectionId || undefined,
          mode: filterMode || undefined,
          format: filterFormat || undefined,
          difficulty: filterDifficulty || undefined,
          language: filterLanguage || undefined,
          unused_only: unusedOnly ? 'true' : undefined,
        })
        if (!cancelled) setItems(data)
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [filterSectionId, filterMode, filterFormat, filterDifficulty, filterLanguage, unusedOnly, reloadToken])

  const visibleItems = items.filter((item) =>
    item.question.toLowerCase().includes(searchText.trim().toLowerCase()),
  )

  function toggleGenSection(id) {
    setGenSectionIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]))
  }

  function toggleSelectAllGen() {
    setGenSectionIds((prev) =>
      prev.length === sections.length ? [] : sections.map((s) => s.id),
    )
  }

  function toggleExpanded(id) {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  async function handleGenerate(e) {
    e.preventDefault()
    if (genSectionIds.length === 0) {
      setGenError(t('startTraining.selectAtLeastOne'))
      return
    }
    setGenError(null)
    setGenerating(true)
    try {
      await api.generateQuestionBankItems(genSectionIds, genMode, genFormat, genDifficulty, genCount)
      setReloadToken((n) => n + 1)
    } catch (err) {
      setGenError(err.message)
    } finally {
      setGenerating(false)
    }
  }

  async function handleDelete(id) {
    if (!window.confirm(t('questionBank.deleteConfirm'))) return
    setError(null)
    setDeletingId(id)
    try {
      await api.deleteQuestionBankItem(id)
      setItems((prev) => prev.filter((item) => item.id !== id))
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  function sectionNamesFor(item) {
    return item.section_ids
      .map((id) => sections.find((s) => s.id === id)?.name || `#${id}`)
      .join(', ')
  }

  return (
    <div className="question-bank-screen">
      <h2>{t('questionBank.title')}</h2>
      <p className="settings-intro">{t('questionBank.intro')}</p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <section className="settings-panel">
        <h3>{t('questionBank.generateTitle')}</h3>
        <form onSubmit={handleGenerate} className="settings-form">
          <div className="field-group">
            <div className="field-label-row">
              <span className="field-label">{t('startTraining.sectionsLegend')}</span>
              {sections.length > 1 && (
                <button type="button" className="btn-link" onClick={toggleSelectAllGen}>
                  {genSectionIds.length === sections.length
                    ? t('startTraining.deselectAll')
                    : t('startTraining.selectAll')}
                </button>
              )}
            </div>
            <div className="section-toggle-list">
              {sections.map((s) => {
                const checked = genSectionIds.includes(s.id)
                return (
                  <label key={s.id} className={`section-toggle${checked ? ' checked' : ''}`}>
                    <input type="checkbox" checked={checked} onChange={() => toggleGenSection(s.id)} />
                    <span>{s.name}</span>
                  </label>
                )
              })}
              {sections.length === 0 && <p>{t('startTraining.noSections')}</p>}
            </div>
          </div>

          <label>
            {t('startTraining.mode')}
            <select value={genMode} onChange={(e) => setGenMode(e.target.value)}>
              <option value="technical">{t('enums.modeTechnical')}</option>
              <option value="behavioral">{t('enums.modeBehavioral')}</option>
              <option value="mixed">{t('enums.modeMixed')}</option>
            </select>
          </label>

          <label>
            {t('startTraining.format')}
            <select value={genFormat} onChange={(e) => setGenFormat(e.target.value)}>
              <option value="open_ended">{t('enums.formatOpenEnded')}</option>
              <option value="quiz">{t('enums.formatQuiz')}</option>
            </select>
          </label>

          <label>
            {t('startTraining.difficulty')}
            <select value={genDifficulty} onChange={(e) => setGenDifficulty(e.target.value)}>
              <option value="easy">{t('enums.difficultyEasy')}</option>
              <option value="medium">{t('enums.difficultyMedium')}</option>
              <option value="hard">{t('enums.difficultyHard')}</option>
            </select>
          </label>

          <label>
            {t('questionBank.generateCount')}
            <input
              type="number"
              min={1}
              max={20}
              value={genCount}
              onChange={(e) => setGenCount(Number(e.target.value))}
            />
          </label>

          {genError && (
            <p className="error" role="alert">
              {genError}
            </p>
          )}

          <button type="submit" disabled={generating}>
            {generating ? t('questionBank.generating') : t('questionBank.generateBtn')}
          </button>
        </form>
      </section>

      <h3>{t('questionBank.listTitle')}</h3>

      <input
        type="search"
        className="question-bank-search"
        placeholder={t('questionBank.searchPlaceholder')}
        aria-label={t('questionBank.searchPlaceholder')}
        value={searchText}
        onChange={(e) => setSearchText(e.target.value)}
      />

      <div className="question-bank-filters">
        <label>
          {t('questionBank.filterSection')}
          <select value={filterSectionId} onChange={(e) => setFilterSectionId(e.target.value)}>
            <option value="">{t('questionBank.filterAll')}</option>
            {sections.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>

        <label>
          {t('startTraining.mode')}
          <select value={filterMode} onChange={(e) => setFilterMode(e.target.value)}>
            <option value="">{t('questionBank.filterAll')}</option>
            <option value="technical">{t('enums.modeTechnical')}</option>
            <option value="behavioral">{t('enums.modeBehavioral')}</option>
            <option value="mixed">{t('enums.modeMixed')}</option>
          </select>
        </label>

        <label>
          {t('startTraining.format')}
          <select value={filterFormat} onChange={(e) => setFilterFormat(e.target.value)}>
            <option value="">{t('questionBank.filterAll')}</option>
            <option value="open_ended">{t('enums.formatOpenEnded')}</option>
            <option value="quiz">{t('enums.formatQuiz')}</option>
          </select>
        </label>

        <label>
          {t('startTraining.difficulty')}
          <select value={filterDifficulty} onChange={(e) => setFilterDifficulty(e.target.value)}>
            <option value="">{t('questionBank.filterAll')}</option>
            <option value="easy">{t('enums.difficultyEasy')}</option>
            <option value="medium">{t('enums.difficultyMedium')}</option>
            <option value="hard">{t('enums.difficultyHard')}</option>
          </select>
        </label>

        <label>
          {t('questionBank.filterLanguage')}
          <select value={filterLanguage} onChange={(e) => setFilterLanguage(e.target.value)}>
            <option value="">{t('questionBank.filterAll')}</option>
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {LANGUAGE_NATIVE_NAMES[code]}
              </option>
            ))}
          </select>
        </label>

        <label className="filter-checkbox">
          <input type="checkbox" checked={unusedOnly} onChange={(e) => setUnusedOnly(e.target.checked)} />
          {t('questionBank.filterUnusedOnly')}
        </label>
      </div>

      {!loading && (
        <p className="question-bank-count">
          {t('questionBank.questionCount', { shown: visibleItems.length, total: items.length })}
        </p>
      )}

      {loading ? (
        <p>{t('common.loading')}</p>
      ) : (
        <ul className="question-bank-list">
          {visibleItems.map((item) => {
            const expanded = expandedIds.has(item.id)
            return (
              <li key={item.id} className="question-bank-item">
                <button
                  type="button"
                  className="question-bank-item-summary"
                  onClick={() => toggleExpanded(item.id)}
                  aria-expanded={expanded}
                >
                  <span className={`status-badge ${item.used_at ? 'used' : 'ready'}`}>
                    {item.used_at ? t('questionBank.statusUsed') : t('questionBank.statusReady')}
                  </span>
                  <span className="question-bank-item-question">{item.question}</span>
                  <span className="question-bank-item-meta">
                    {t(MODE_KEYS[item.mode] || item.mode)} · {t(FORMAT_KEYS[item.format] || item.format)} ·{' '}
                    {t(DIFFICULTY_KEYS[item.difficulty] || item.difficulty)}
                  </span>
                  <span className="question-bank-chevron" aria-hidden="true">
                    {expanded ? '▾' : '▸'}
                  </span>
                </button>

                {expanded && (
                  <div className="question-bank-item-details">
                    <p className="question-bank-item-meta">{sectionNamesFor(item)}</p>
                    {item.options && (
                      <ul className="question-bank-options">
                        {item.options.map((opt, idx) => (
                          <li key={idx} className={idx === item.correct_index ? 'correct' : ''}>
                            {opt}
                          </li>
                        ))}
                      </ul>
                    )}
                    {item.explanation && <p className="explanation">{item.explanation}</p>}
                    <button
                      type="button"
                      className="btn-danger"
                      onClick={() => handleDelete(item.id)}
                      disabled={deletingId === item.id}
                    >
                      {deletingId === item.id ? t('questionBank.deleting') : t('questionBank.deleteBtn')}
                    </button>
                  </div>
                )}
              </li>
            )
          })}
          {items.length === 0 && <li className="section-list-empty">{t('questionBank.empty')}</li>}
          {items.length > 0 && visibleItems.length === 0 && (
            <li className="section-list-empty">{t('questionBank.noSearchResults')}</li>
          )}
        </ul>
      )}
    </div>
  )
}
