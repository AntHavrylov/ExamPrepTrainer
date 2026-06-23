import { useEffect, useState } from 'react'
import { api } from '../api'

export default function SectionsScreen() {
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
    if (!window.confirm(`Delete "${name}" and all its notes? This can't be undone.`)) return
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

  if (loading) return <p>Loading sections...</p>

  return (
    <div className="sections-screen">
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      <div className="sections-layout">
        <section className="sections-panel">
          <h2>Your sections</h2>
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
                    aria-label={`Delete ${s.name}`}
                    title="Delete section"
                  >
                    ×
                  </button>
                </div>
              </li>
            ))}
            {sections.length === 0 && (
              <li className="section-list-empty">No sections yet — create one to get started.</li>
            )}
          </ul>
        </section>

        <section className="create-section-panel">
          <h3>Create new section</h3>
          <form onSubmit={handleCreateSection} className="create-section-form">
            <input
              placeholder="Section name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              required
            />
            <input
              placeholder="Description (optional)"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
            />
            <button type="submit">Create section</button>
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
                  Edit
                </button>
                <button className="btn-danger" onClick={() => handleDeleteDocument(doc.id)}>
                  Delete
                </button>
              </li>
            ))}
            {selectedSection.documents.length === 0 && <li>No notes yet.</li>}
          </ul>

          <form onSubmit={handleSaveDocument} className="document-form">
            <input
              placeholder="Title"
              value={docTitle}
              onChange={(e) => setDocTitle(e.target.value)}
              required
            />
            <textarea
              placeholder="Paste your notes here..."
              value={docContent}
              onChange={(e) => setDocContent(e.target.value)}
              rows={6}
              required
            />
            <button type="submit">{editingDocId ? 'Save changes' : 'Add notes'}</button>
            {editingDocId && (
              <button type="button" className="btn-secondary" onClick={resetDocForm}>
                Cancel
              </button>
            )}
          </form>

          <label className="document-upload">
            Or import a .md/.txt file:
            <input type="file" accept=".md,.txt" onChange={handleUploadFile} />
          </label>
        </section>
      )}
    </div>
  )
}
