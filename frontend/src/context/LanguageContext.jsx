import { createContext, useContext, useEffect, useState } from 'react'
import { SUPPORTED_LANGUAGES, translations } from '../i18n/translations'

const LanguageContext = createContext(null)
const LANGUAGE_KEY = 'prep_trainer_language'

function getInitialLanguage() {
  const stored = localStorage.getItem(LANGUAGE_KEY)
  if (SUPPORTED_LANGUAGES.includes(stored)) return stored

  const browserLanguage = (navigator.language || 'en').slice(0, 2).toLowerCase()
  return SUPPORTED_LANGUAGES.includes(browserLanguage) ? browserLanguage : 'en'
}

function interpolate(template, vars) {
  if (!vars) return template
  return Object.entries(vars).reduce(
    (str, [key, value]) => str.replaceAll(`{${key}}`, value),
    template,
  )
}

export function LanguageProvider({ children }) {
  const [language, setLanguageState] = useState(getInitialLanguage)

  useEffect(() => {
    localStorage.setItem(LANGUAGE_KEY, language)
  }, [language])

  function setLanguage(lang) {
    if (SUPPORTED_LANGUAGES.includes(lang)) setLanguageState(lang)
  }

  function t(key, vars) {
    const dict = translations[language] || translations.en
    const template = dict[key] ?? translations.en[key] ?? key
    return interpolate(template, vars)
  }

  const value = { language, setLanguage, t }
  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components -- hook lives alongside its provider
export function useLanguage() {
  const ctx = useContext(LanguageContext)
  if (!ctx) throw new Error('useLanguage must be used within LanguageProvider')
  return ctx
}
