import { useEffect, useState } from 'react'
import { api } from '../api'
import { useLanguage } from '../context/LanguageContext'

export default function SectionsScreen() {
  const { t } = useLanguage()
  const [sections, setSections] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [newName, setNewName] = useState('')
  const [newDescription, setNewDescription] = useState('')
  const [selectedSection, setSelectedSection] = useState(null)
  const [docTitle, setDocTitle] = useState('')
  const [docContent, setDocContent] = useState('')
  const [editingDocId, setEditingDocId] = useState(null)

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
      await loadSections()
    } catch (err) {
      setError(err.message)
    }
  }

  async function openSection(id) {
    setError(null)
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

  return (
    <div className="sections-screen">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="sections-layout">
        <section className="sections-panel">
          <h2>{t('sections.yourSections')}</h2>
          <ul className="section-list">
            {sections.map((s) => (
              <li key={s.id}>
                <div className={`section-card${selectedSection?.id === s.id ? ' active' : ''}`}>
                  <button className="section-card-open" onClick={() => openSection(s.id)}>
                    {s.name}
                  </button>
                  <button
                    type="button"
                    className="section-card-delete"
                    onClick={() => handleDeleteSection(s.id, s.name)}
                    aria-label={t('sections.deleteSectionAria', { name: s.name })}
                    title={t('sections.deleteSectionTitle')}
                  >
                    ×
                  </button>
                </div>
              </li>
            ))}
            {sections.length === 0 && (
              <li className="section-list-empty">{t('sections.empty')}</li>
            )}
          </ul>
        </section>

        <section className="create-section-panel">
          <h3>{t('sections.createNew')}</h3>
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
            <button type="submit">{t('sections.createBtn')}</button>
          </form>
        </section>
      </div>

      {selectedSection && (
        <section>
          <h3>{selectedSection.name}</h3>
          <ul className="document-list">
            {selectedSection.documents.map((doc) => (
              <li key={doc.id}>
                <strong>{doc.title}</strong>
                <p>{doc.content}</p>
                <button className="btn-secondary" onClick={() => startEditDocument(doc)}>
                  {t('sections.editBtn')}
                </button>
                <button className="btn-danger" onClick={() => handleDeleteDocument(doc.id)}>
                  {t('sections.deleteBtn')}
                </button>
              </li>
            ))}
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
        </section>
      )}
    </div>
  )
}
