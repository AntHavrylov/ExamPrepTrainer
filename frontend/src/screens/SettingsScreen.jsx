import { useEffect, useState } from 'react'
import { api } from '../api'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import { LANGUAGE_NATIVE_NAMES, SUPPORTED_LANGUAGES } from '../i18n/translations'

export default function SettingsScreen() {
  const { user } = useAuth()
  const { language, setLanguage, t } = useLanguage()
  const [status, setStatus] = useState(null)
  const [models, setModels] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [toast, setToast] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [selectedModel, setSelectedModel] = useState('')
  const [modelFilter, setModelFilter] = useState('')
  const [saving, setSaving] = useState(false)
  const [removing, setRemoving] = useState(false)
  const [savingLanguage, setSavingLanguage] = useState(false)
  const [sessionLength, setSessionLength] = useState(user?.session_length ?? 5)
  const [savingSessionLength, setSavingSessionLength] = useState(false)

  function showToast() {
    setToast(t('common.saved'))
    setTimeout(() => setToast(''), 2000)
  }

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
      showToast()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  async function handleRemove() {
    if (!window.confirm(t('settings.removeConfirm'))) return
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

  async function handleLanguageChange(e) {
    const next = e.target.value
    setError(null)
    setSavingLanguage(true)
    try {
      await api.updateLanguage(next)
      setLanguage(next)
      showToast()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingLanguage(false)
    }
  }

  function handleSessionLengthChange(e) {
    setSessionLength(Number(e.target.value))
  }

  async function handleSessionLengthSave(e) {
    e.preventDefault()
    setError(null)
    setSavingSessionLength(true)
    try {
      await api.updateSessionLength(sessionLength)
      showToast()
    } catch (err) {
      setError(err.message)
    } finally {
      setSavingSessionLength(false)
    }
  }

  if (loading) return <p>{t('settings.loading')}</p>

  return (
    <div className="settings-screen">
      <h2>{t('settings.languageTitle')}</h2>
      <p className="settings-intro">{t('settings.languageIntro')}</p>

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {toast && <p className="settings-toast" aria-live="polite">{toast}</p>}

      <section className="settings-panel">
        <label>
          {t('settings.languageTitle')}
          <select value={language} onChange={handleLanguageChange} disabled={savingLanguage}>
            {SUPPORTED_LANGUAGES.map((code) => (
              <option key={code} value={code}>
                {LANGUAGE_NATIVE_NAMES[code]}
              </option>
            ))}
          </select>
        </label>
      </section>

      <h2>{t('settings.sessionLengthTitle')}</h2>
      <p className="settings-intro">{t('settings.sessionLengthIntro')}</p>

      <section className="settings-panel">
        <form onSubmit={handleSessionLengthSave} className="settings-form">
          <label>
            {t('settings.sessionLengthTitle')}
            <input
              type="number"
              min={1}
              max={50}
              value={sessionLength}
              onChange={handleSessionLengthChange}
              disabled={savingSessionLength}
              className="session-length-input"
            />
          </label>
          <p className="settings-sub">{t('settings.sessionLengthRange')}</p>
          <button type="submit" disabled={savingSessionLength}>
            {savingSessionLength ? t('settings.saving') : t('settings.sessionLengthSave')}
          </button>
        </form>
      </section>

      <h2>{t('settings.title')}</h2>
      <p className="settings-intro">{t('settings.intro')}</p>

      {status?.has_key ? (
        <section className="settings-panel">
          <p>
            {t('settings.usingKeyPrefix')} <strong>{status.model}</strong>.
          </p>
          <button type="button" className="btn-danger" onClick={handleRemove} disabled={removing}>
            {removing ? t('settings.removing') : t('settings.removeKey')}
          </button>
        </section>
      ) : (
        <section className="settings-panel">
          <form onSubmit={handleSave} className="settings-form">
            <label>
              {t('settings.apiKeyLabel')}
              <input
                type="password"
                placeholder="sk-or-..."
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                required
              />
            </label>

            <label>
              {t('settings.filterModelsLabel')}
              <input
                type="text"
                placeholder={t('settings.filterPlaceholder')}
                value={modelFilter}
                onChange={handleFilterChange}
              />
            </label>

            <label>
              {t('settings.modelLabel')}
              <select value={selectedModel} onChange={(e) => setSelectedModel(e.target.value)}>
                {filteredModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
                {filteredModels.length === 0 && <option value="">{t('settings.noModelsMatch')}</option>}
              </select>
            </label>

            <button type="submit" disabled={saving || !apiKey || !selectedModel}>
              {saving ? t('settings.saving') : t('settings.saveKey')}
            </button>
          </form>
        </section>
      )}
    </div>
  )
}
