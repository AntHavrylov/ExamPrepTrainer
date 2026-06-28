import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'

function IconSearch() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="8" />
      <path d="m21 21-4.35-4.35" />
    </svg>
  )
}

function IconPlus() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 5v14M5 12h14" />
    </svg>
  )
}

function IconTrash() {
  return (
    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6l-1 14H6L5 6" />
      <path d="M10 11v6M14 11v6" />
      <path d="M9 6V4h6v2" />
    </svg>
  )
}

function SectionIcon({ name }) {
  return (
    <span className="section-card-icon">
      {(name || '?').slice(0, 1).toUpperCase()}
    </span>
  )
}

export default function SectionsScreen() {
  const { t } = useLanguage()
  const [sections, setSections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [selectedSection, setSelectedSection] = useState(null)
  const [docTitle, setDocTitle] = useState('')
  const [docContent, setDocContent] = useState('')
  const [editingDocId, setEditingDocId] = useState(null)
  const [expandedDocIds, setExpandedDocIds] = useState(() => new Set())

  const DOC_PREVIEW_LEN = 150

  function toggleDocExpand(id) {
    setExpandedDocIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  useEffect(() => {
    api
      .listSections()
      .then(setSections)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  async function loadSections() {
    try {
      const data = await api.listSections()
      setSections(data)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleCreateSection(e) {
    e.preventDefault()
    setError(null)
    try {
      await api.createSection(newName, newDescription)
      setNewName('')
      setNewDescription('')
      setShowCreateForm(false)
      await loadSections()
    } catch (err) {
      setError(err.message)
    }
  }

  async function openSection(id) {
    setError(null)
    setExpandedDocIds(new Set())
    try {
      const data = await api.getSection(id)
      setSelectedSection(data)
    } catch (err) {
      setError(err.message)
    }
  }

  async function handleDeleteSection(id, name) {
    if (!window.confirm(t('sections.deleteConfirm', { name }))) return
    setError(null)
    try {
      await api.deleteSection(id)
      if (selectedSection?.id === id) {
        resetDocForm()
        setSelectedSection(null)
      }
      await loadSections()
    } catch (err) {
      setError(err.message)
    }
  }

  function resetDocForm() {
    setEditingDocId(null)
    setDocTitle('')
    setDocContent('')
  }

  async function handleSaveDocument(e) {
    e.preventDefault()
    if (!selectedSection) return
    setError(null)
    try {
      if (editingDocId) {
        await api.updateDocument(editingDocId, docTitle, docContent)
      } else {
        await api.addDocument(selectedSection.id, docTitle, docContent)
      }
      resetDocForm()
      await openSection(selectedSection.id)
    } catch (err) {
      setError(err.message)
    }
  }

  function startEditDocument(doc) {
    setEditingDocId(doc.id)
    setDocTitle(doc.title)
    setDocContent(doc.content)
  }

  async function handleUploadFile(e) {
    const file = e.target.files?.[0]
    if (!file || !selectedSection) return
    setError(null)
    try {
      await api.uploadDocument(selectedSection.id, file)
      await openSection(selectedSection.id)
    } catch (err) {
      setError(err.message)
    } finally {
      e.target.value = ''
    }
  }

  async function handleDeleteDocument(id) {
    setError(null)
    try {
      await api.deleteDocument(id)
      if (editingDocId === id) resetDocForm()
      await openSection(selectedSection.id)
    } catch (err) {
      setError(err.message)
    }
  }

  if (loading) return <p>{t('sections.loading')}</p>

  const filtered = sections.filter((s) =>
    s.name.toLowerCase().includes(search.trim().toLowerCase()),
  )

  return (
    <div className="sections-screen">
      {error && (
        <p className="error" role="alert">{error}</p>
      )}

      <div className="sections-toolbar">
        <div className="sections-search-wrap">
          <span className="sections-search-icon"><IconSearch /></span>
          <input
            type="search"
            className="sections-search"
            placeholder="Search sections…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button
          type="button"
          className="sections-new-btn"
          onClick={() => setShowCreateForm((v) => !v)}
        >
          <IconPlus />
          {t('sections.createNew')}
        </button>
      </div>

      {showCreateForm && (
        <div className="create-section-panel" style={{ marginBottom: 20 }}>
          <h3 style={{ marginTop: 0 }}>{t('sections.createNew')}</h3>
          <form onSubmit={handleCreateSection} className="create-section-form">
            <input
              placeholder={t('sections.namePlaceholder')}
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
            />
            <input
              placeholder={t('sections.descPlaceholder')}
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
            />
            <div style={{ display: 'flex', gap: 8 }}>
              <button type="submit">{t('sections.createBtn')}</button>
              <button type="button" className="btn-secondary" onClick={() => setShowCreateForm(false)}>
                {t('sections.cancel')}
              </button>
            </div>
          </form>
        </div>
      )}

      {filtered.length === 0 && !showCreateForm && (
        <p style={{ color: 'var(--text-2)' }}>
          {sections.length === 0 ? t('sections.empty') : t('questionBank.noSearchResults')}
        </p>
      )}

      <div className="section-cards-grid">
        {filtered.map((s) => {
          const docCount = s.document_count ?? 0
          const isActive = selectedSection?.id === s.id
          return (
            <div
              key={s.id}
              className={`section-card-v2${isActive ? ' active' : ''}`}
            >
              <div className="section-card-header">
                <SectionIcon name={s.name} />
                <span className="section-card-badge ready">
                  {docCount} {docCount === 1 ? 'doc' : 'docs'}
                </span>
              </div>

              <div className="section-card-body">
                <div className="section-card-name">{s.name}</div>
                {s.description && (
                  <div className="section-card-meta">{s.description}</div>
                )}
              </div>

              <div className="section-card-progress">
                <div className="section-card-progress-fill" style={{ width: `${Math.min(docCount * 20, 100)}%` }} />
              </div>

              <div className="section-card-actions">
                <button
                  type="button"
                  className="section-card-train-btn"
                  onClick={() => openSection(s.id)}
                >
                  {isActive ? t('sections.editBtn') : 'Open'}
                </button>
                <button
                  type="button"
                  className="section-card-delete-btn"
                  onClick={() => handleDeleteSection(s.id, s.name)}
                  aria-label={t('sections.deleteSectionAria', { name: s.name })}
                  title={t('sections.deleteSectionTitle')}
                >
                  <IconTrash />
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {selectedSection && (
        <div className="section-detail">
          <h3>{selectedSection.name}</h3>

          <ul className="document-list">
            {selectedSection.documents.map((doc) => {
              const isLong = doc.content.length > DOC_PREVIEW_LEN
              const isExpanded = expandedDocIds.has(doc.id)
              return (
                <li key={doc.id}>
                  <strong>{doc.title}</strong>
                  <p className="doc-preview">
                    {isLong && !isExpanded ? doc.content.slice(0, DOC_PREVIEW_LEN) + '…' : doc.content}
                  </p>
                  {isLong && (
                    <button type="button" className="btn-link" onClick={() => toggleDocExpand(doc.id)}>
                      {isExpanded ? t('sections.showLess') : t('sections.showMore')}
                    </button>
                  )}
                  <div className="doc-actions">
                    <button className="btn-secondary" onClick={() => startEditDocument(doc)}>
                      {t('sections.editBtn')}
                    </button>
                    <button className="btn-danger" onClick={() => handleDeleteDocument(doc.id)}>
                      {t('sections.deleteBtn')}
                    </button>
                  </div>
                </li>
              )
            })}
            {selectedSection.documents.length === 0 && <li>{t('sections.notesNone')}</li>}
          </ul>

          <form onSubmit={handleSaveDocument} className="document-form">
            <input
              placeholder={t('sections.titlePlaceholder')}
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              required
            />
            <textarea
              placeholder={t('sections.notesPlaceholder')}
              value={docContent}
              onChange={(e) => setDocContent(e.target.value)}
              rows={6}
              required
            />
            <p className="char-counter">
              {docContent.length.toLocaleString()} / 50,000
            </p>
            <button type="submit">{editingDocId ? t('sections.saveChanges') : t('sections.addNotes')}</button>
            {editingDocId && (
              <button type="button" className="btn-secondary" onClick={resetDocForm}>
                {t('sections.cancel')}
              </button>
            )}
          </form>

          <label className="document-upload">
            {t('sections.importLabel')}
            <input type="file" accept=".md,.txt" onChange={handleUploadFile} />
          </label>
        </div>
      )}
    </div>
  )
}
