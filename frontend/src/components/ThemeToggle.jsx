import { useLanguage } from '../context/LanguageContext'
import { useTheme } from '../hooks/useTheme'

export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme()
  const { t } = useLanguage()

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={toggleTheme}
      aria-label={t('app.toggleThemeAria')}
      title={t('app.toggleThemeAria')}
    >
      {theme === 'dark' ? '☀️' : '🌙'}
    </button>
  )
}
