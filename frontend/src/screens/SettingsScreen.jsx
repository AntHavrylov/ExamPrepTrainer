import { useEffect, useState } from 'react'
import { api } from '../api'

export default function SettingsScreen() {
  const [status, setStatus] = useState(null)
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [apiKey, setApiKey] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [modelFilter, setModelFilter] = useState('')
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState(false)

  useEffect(() => {
    Promise.all([api.getApiKeyStatus(), api.listModels()])
      .then(([statusData, modelsData]) => {
        setStatus(statusData)
        setModels(modelsData)
        if (modelsData.length > 0) setSelectedModel(modelsData[0].id)
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  const filteredModels = models.filter((m) => {
    const q = modelFilter.trim().toLowerCase()
    if (!q) return true
    return m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q)
  })

  function handleFilterChange(e) {
    const value = e.target.value
    setModelFilter(value)
    const q = value.trim().toLowerCase()
    const matches = models.filter(
      (m) => !q || m.id.toLowerCase().includes(q) || m.name.toLowerCase().includes(q),
    )
    if (matches.length > 0 && !matches.some((m) => m.id === selectedModel)) {
      setSelectedModel(matches[0].id)
    }
  }

  async function handleSave(e) {
    e.preventDefault()
    setError(null)
    setSaving(true)
    try {
      const updated = await api.saveApiKey(apiKey, selectedModel)
      setStatus(updated)
      setApiKey('')
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleRemove() {
    if (!window.confirm("Remove your saved API key? This can't be undone.")) return
    setError(null)
    setRemoving(true)
    try {
      await api.deleteApiKey()
      setStatus({ has_key: false, model: null })
    } catch (err) {
      setError(err.message)
    } finally {
      setRemoving(false)
    }
  }

  if (loading) return <p>Loading settings...</p>

  return (
    <div className="settings-screen">
      <h2>AI settings</h2>
      <p className="settings-intro">
        Connect your own OpenRouter API key and pick a model. A key is required to use AI
        features (generating and scoring questions) — there's no shared default key.
      </p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {status?.has_key ? (
        <section className="settings-panel">
          <p>
            Using your own OpenRouter key with model <strong>{status.model}</strong>.
          </p>
          <button type="button" className="btn-danger" onClick={handleRemove} disabled={removing}>
            {removing ? 'Removing...' : 'Remove key'}
          </button>
        </section>
      ) : (
        <section className="settings-panel">
          <form onSubmit={handleSave} className="settings-form">
            <label>
              OpenRouter API key
              <input
                type="password"
                placeholder="sk-or-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                required
              />
            </label>

            <label>
              Filter models
              <input
                type="text"
                placeholder="Filter by name or id..."
                value={modelFilter}
                onChange={handleFilterChange}
              />
            </label>

            <label>
              Model
              <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
                {filteredModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
                {filteredModels.length === 0 && <option value="">No models match</option>}
              </select>
            </label>

            <button type="submit" disabled={saving || !apiKey || !selectedModel}>
              {saving ? 'Saving...' : 'Save key'}
            </button>
          </form>
        </section>
      )}
    </div>
  )
}
