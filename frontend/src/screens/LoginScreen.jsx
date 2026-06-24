import { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { useLanguage } from '../context/LanguageContext'
import { LANGUAGE_NATIVE_NAMES, SUPPORTED_LANGUAGES } from '../i18n/translations'

export default function LoginScreen() {
  const { login, register } = useAuth()
  const { language, setLanguage, t } = useLanguage()
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      if (mode === 'login') {
        await login(email, password)
      } else {
        await register(email, password, language)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="auth-screen">
      <select
        className="auth-language-select"
        value={language}
        onChange={(e) => setLanguage(e.target.value)}
        aria-label={t('settings.languageTitle')}
      >
        {SUPPORTED_LANGUAGES.map((code) => (
          <option key={code} value={code}>
            {LANGUAGE_NATIVE_NAMES[code]}
          </option>
        ))}
      </select>

      <h1 className="auth-title">{t('app.title')}</h1>
      <h2>{mode === 'login' ? t('login.titleLogin') : t('login.titleRegister')}</h2>
      <form onSubmit={handleSubmit}>
        <label>
          {t('login.email')}
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
          />
        </label>
        <label>
          {t('login.password')}
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit" disabled={submitting}>
          {submitting
            ? t('login.pleaseWait')
            : mode === 'login'
              ? t('login.titleLogin')
              : t('login.titleRegister')}
        </button>
      </form>
      <button type="button" className="link" onClick={() => setMode(mode === 'login' ? 'register' : 'login')}>
        {mode === 'login' ? t('login.toggleToRegister') : t('login.toggleToLogin')}
      </button>
    </div>
  )
}
