import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'
import { LANGUAGE_NATIVE_NAMES, SUPPORTED_LANGUAGES } from '../i18n/translations'

const MAX_QUEUE = 2

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

function FilterPills({ label, value, onChange, options }) {
  return (
    <div className="filter-pills">
      <button
        type="button"
        className={`filter-pill${value === '' ? ' active' : ''}`}
        onClick={() => onChange('')}
      >
        All
      </button>
      {options.map(({ val, label: lbl }) => (
        <button
          key={val}
          type="button"
          className={`filter-pill${value === val ? ' active' : ''}`}
          onClick={() => onChange(val === value ? '' : val)}
        >
          {lbl}
        </button>
      ))}
    </div>
  )
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
  const [activeJobs, setActiveJobs] = useState([])
  const [genError, setGenError] = useState(null)
  const [genSuccess, setGenSuccess] = useState(null)

  const [deletingId, setDeletingId] = useState(null)
  const [deletingBulk, setDeletingBulk] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const [expandedIds, setExpandedIds] = useState(() => new Set())
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const initialLoadDone = useRef(false)

  useEffect(() => {
    api
      .listSections()
      .then(setSections)
      .catch((err) => setError(err.message))
  }, [])

  useEffect(() => {
    let cancelled = false

    async function load() {
      if (!initialLoadDone.current) setLoading(true)
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
        if (!cancelled) {
          setItems(data)
          setSelectedIds(new Set())
          initialLoadDone.current = true
        }
      } catch (err) {
        if (!cancelled) setError(err.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    load()
    return () => { cancelled = true }
  }, [filterSectionId, filterMode, filterFormat, filterDifficulty, filterLanguage, unusedOnly, reloadToken])

  // Poll active generation jobs every 2 seconds
  useEffect(() => {
    if (activeJobs.length === 0) return
    const id = setTimeout(async () => {
      const results = await Promise.allSettled(activeJobs.map((j) => api.getGenerationJob(j.job_id)))
      const still = []
      let needsReload = false
      const errors = []
      let totalDone = 0

      results.forEach((res, i) => {
        if (res.status === 'rejected') { still.push(activeJobs[i]); return }
        const updated = res.value
        if (updated.status === 'done') {
          needsReload = true
          totalDone += updated.count
        } else if (updated.status === 'failed') {
          errors.push(updated.error || t('questionBank.jobFailed'))
        } else {
          still.push(updated)
        }
      })

      if (needsReload) {
        setReloadToken((n) => n + 1)
        setGenSuccess(t('questionBank.jobDone', { count: totalDone }))
      }
      if (errors.length > 0) setGenError(errors.join('; '))
      setActiveJobs(still)
    }, 2000)
    return () => clearTimeout(id)
  }, [activeJobs])

  const visibleItems = items.filter((item) =>
    item.question.toLowerCase().includes(searchText.trim().toLowerCase()),
  )

  const visibleSelectedCount = visibleItems.filter((i) => selectedIds.has(i.id)).length
  const allVisibleSelected = visibleItems.length > 0 && visibleSelectedCount === visibleItems.length

  function toggleSelected(id) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  function toggleSelectAllVisible() {
    if (allVisibleSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        visibleItems.forEach((i) => next.delete(i.id))
        return next
      })
    } else {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        visibleItems.forEach((i) => next.add(i.id))
        return next
      })
    }
  }

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
    setGenSuccess(null)
    try {
      const { job_id } = await api.generateQuestionBankItems(genSectionIds, genMode, genFormat, genDifficulty, genCount)
      setActiveJobs((prev) => [...prev, { job_id, status: 'pending', count: 0, error: null }])
    } catch (err) {
      setGenError(err.message)
    }
  }

  async function handleDelete(id) {
    if (!window.confirm(t('questionBank.deleteConfirm'))) return
    setError(null)
    setDeletingId(id)
    try {
      await api.deleteQuestionBankItem(id)
      setItems((prev) => prev.filter((item) => item.id !== id))
      setSelectedIds((prev) => { const next = new Set(prev); next.delete(id); return next })
    } catch (err) {
      setError(err.message)
    } finally {
      setDeletingId(null)
    }
  }

  async function handleDeleteSelected() {
    if (!window.confirm(t('questionBank.deleteSelectedConfirm', { count: selectedIds.size }))) return
    setError(null)
    setDeletingBulk(true)
    const ids = [...selectedIds]
    try {
      await Promise.all(ids.map((id) => api.deleteQuestionBankItem(id)))
      setItems((prev) => prev.filter((item) => !ids.includes(item.id)))
      setSelectedIds(new Set())
    } catch (err) {
      setError(err.message)
      setReloadToken((n) => n + 1)
    } finally {
      setDeletingBulk(false)
    }
  }

  function sectionNamesFor(item) {
    return item.section_ids
      .map((id) => sections.find((s) => s.id === id)?.name || `#${id}`)
      .join(', ')
  }

  return (
    <div className="question-bank-screen">
      {genSuccess && (
        <div className="gen-notification-banner" role="status">
          <span>{genSuccess}</span>
          <button
            type="button"
            className="gen-notification-close"
            aria-label="Dismiss"
            onClick={() => setGenSuccess(null)}
          >
            ×
          </button>
        </div>
      )}

      <p className="settings-intro">{t('questionBank.intro')}</p>

      {error && (
        <p className="error" role="alert">{error}</p>
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
            <p className="error" role="alert">{genError}</p>
          )}

          <button type="submit" disabled={activeJobs.length >= MAX_QUEUE}>
            {activeJobs.length >= MAX_QUEUE
              ? t('questionBank.queueFull', { max: MAX_QUEUE })
              : t('questionBank.generateBtn')}
          </button>

          {activeJobs.map((job) => (
            <div key={job.job_id} className="loading-block">
              <span className="spinner" aria-hidden="true" />
              <span>{t('questionBank.jobPending')}</span>
            </div>
          ))}
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

      {sections.length > 0 && (
        <FilterPills
          value={filterSectionId}
          onChange={setFilterSectionId}
          options={sections.map((s) => ({ val: String(s.id), label: s.name }))}
        />
      )}

      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginBottom: 12 }}>
        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)' }}>
          {t('startTraining.mode')}
          <select value={filterMode} onChange={(e) => setFilterMode(e.target.value)} style={{ fontSize: 13, padding: '3px 8px' }}>
            <option value="">{t('questionBank.filterAll')}</option>
            <option value="technical">{t('enums.modeTechnical')}</option>
            <option value="behavioral">{t('enums.modeBehavioral')}</option>
            <option value="mixed">{t('enums.modeMixed')}</option>
          </select>
        </label>

        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)' }}>
          {t('startTraining.format')}
          <select value={filterFormat} onChange={(e) => setFilterFormat(e.target.value)} style={{ fontSize: 13, padding: '3px 8px' }}>
            <option value="">{t('questionBank.filterAll')}</option>
            <option value="open_ended">{t('enums.formatOpenEnded')}</option>
            <option value="quiz">{t('enums.formatQuiz')}</option>
          </select>
        </label>

        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)' }}>
          {t('startTraining.difficulty')}
          <select value={filterDifficulty} onChange={(e) => setFilterDifficulty(e.target.value)} style={{ fontSize: 13, padding: '3px 8px' }}>
            <option value="">{t('questionBank.filterAll')}</option>
            <option value="easy">{t('enums.difficultyEasy')}</option>
            <option value="medium">{t('enums.difficultyMedium')}</option>
            <option value="hard">{t('enums.difficultyHard')}</option>
          </select>
        </label>

        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)' }}>
          {t('questionBank.filterLanguage')}
          <select value={filterLanguage} onChange={(e) => setFilterLanguage(e.target.value)} style={{ fontSize: 13, padding: '3px 8px' }}>
            <option value="">{t('questionBank.filterAll')}</option>
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>{LANGUAGE_NATIVE_NAMES[code]}</option>
            ))}
          </select>
        </label>

        <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, color: 'var(--text-2)', cursor: 'pointer' }}>
          <input type="checkbox" checked={unusedOnly} onChange={(e) => setUnusedOnly(e.target.checked)} style={{ accentColor: 'var(--accent)' }} />
          {t('questionBank.filterUnusedOnly')}
        </label>
      </div>

      <div className="question-bank-list-header">
        <label className="question-bank-select-all">
          <input
            type="checkbox"
            checked={allVisibleSelected}
            ref={(el) => {
              if (el) el.indeterminate = visibleSelectedCount > 0 && !allVisibleSelected
            }}
            onChange={toggleSelectAllVisible}
            disabled={visibleItems.length === 0}
          />
          <span className="question-bank-count">
            {t('questionBank.questionCount', { shown: visibleItems.length, total: items.length })}
          </span>
        </label>

        {selectedIds.size > 0 && (
          <button
            type="button"
            className="btn-danger"
            onClick={handleDeleteSelected}
            disabled={deletingBulk}
          >
            {deletingBulk
              ? t('questionBank.deleting')
              : t('questionBank.deleteSelected', { count: selectedIds.size })}
          </button>
        )}
      </div>

      {loading ? (
        <p>{t('common.loading')}</p>
      ) : (
        <ul className="question-bank-table">
          {visibleItems.map((item, idx) => {
            const expanded = expandedIds.has(item.id)
            const selected = selectedIds.has(item.id)
            return (
              <li key={item.id} className={`question-bank-item${selected ? ' selected' : ''}`}>
                <div className="question-bank-item-row">
                  <label className="question-bank-item-checkbox" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected}
                      onChange={() => toggleSelected(item.id)}
                    />
                  </label>

                  <span className="question-bank-item-idx">{idx + 1}</span>

                  <button
                    type="button"
                    className="question-bank-item-summary"
                    onClick={() => toggleExpanded(item.id)}
                    aria-expanded={expanded}
                  >
                    <span className="question-bank-item-body">
                      <span className="question-bank-item-section">{sectionNamesFor(item)}</span>
                      <span className={`question-bank-item-question${expanded ? ' expanded' : ''}`}>
                        {item.question}
                      </span>
                      <span className="question-bank-item-meta">
                        {t(MODE_KEYS[item.mode] || item.mode)} · {t(FORMAT_KEYS[item.format] || item.format)} ·{' '}
                        {t(DIFFICULTY_KEYS[item.difficulty] || item.difficulty)}
                      </span>
                    </span>
                    <span className={`status-badge ${item.used_at ? 'used' : 'ready'}`}>
                      {item.used_at ? t('questionBank.statusUsed') : t('questionBank.statusReady')}
                    </span>
                    <span className="question-bank-chevron" aria-hidden="true">
                      {expanded ? '▾' : '▸'}
                    </span>
                  </button>
                </div>

                {expanded && (
                  <div className="question-bank-item-details">
                    {item.options && (
                      <ul className="question-bank-options">
                        {item.options.map((opt, i) => (
                          <li key={i} className={i === item.correct_index ? 'correct' : ''}>
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
          {items.length === 0 && <li style={{ padding: '16px 18px', color: 'var(--text-2)' }}>{t('questionBank.empty')}</li>}
          {items.length > 0 && visibleItems.length === 0 && (
            <li style={{ padding: '16px 18px', color: 'var(--text-2)' }}>{t('questionBank.noSearchResults')}</li>
          )}
        </ul>
      )}
    </div>
  )
}
