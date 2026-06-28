import { useEffect, useState } from 'react'
import './App.css'
import Sidebar from './components/Sidebar'
import { ACTIVE_SESSION_KEY } from './api'
import { LAST_TRAINING_SETTINGS_KEY, PRE_SELECT_SECTIONS_KEY } from './constants'
import { AuthProvider, useAuth } from './context/AuthContext'
import { LanguageProvider, useLanguage } from './context/LanguageContext'
import { useTheme } from './hooks/useTheme'
import LoginScreen from './screens/LoginScreen'
import SectionsScreen from './screens/SectionsScreen'
import StartTrainingScreen from './screens/StartTrainingScreen'
import TrainingScreen from './screens/TrainingScreen'
import SummaryScreen from './screens/SummaryScreen'
import ProgressScreen from './screens/ProgressScreen'
import SettingsScreen from './screens/SettingsScreen'
import QuestionBankScreen from './screens/QuestionBankScreen'

function getInitialActiveSessionId() {
  const stored = localStorage.getItem(ACTIVE_SESSION_KEY)
  return stored ? Number(stored) : null
}

const VIEW_META = {
  sections: ['Sections', 'Manage your study materials'],
  'start-training': ['Start Training', 'Configure your session'],
  training: ['Training', 'Stay focused'],
  summary: ['Session Summary', 'Review your results'],
  progress: ['Progress', 'Track your improvement'],
  settings: ['Settings', 'App preferences'],
  'question-bank': ['Question Bank', 'Browse & generate questions'],
}

function IconSun() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M2 12h2M20 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4" />
    </svg>
  )
}

function IconMoon() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5Z" />
    </svg>
  )
}

function AppHeader({ view, theme, onToggleTheme }) {
  const [title, subtitle] = VIEW_META[view] || ['', '']
  return (
    <header className="app-header">
      <div className="app-header-title">
        <h1>{title}</h1>
        {subtitle && <span className="app-header-sub">{subtitle}</span>}
      </div>
      <div className="app-header-actions">
        <button
          type="button"
          className="app-header-theme-btn"
          onClick={onToggleTheme}
          aria-label="Toggle theme"
          title="Toggle theme"
        >
          {theme === 'dark' ? <IconSun /> : <IconMoon />}
        </button>
      </div>
    </header>
  )
}

function AppShell() {
  const { token, user, authLoading, logout } = useAuth()
  const { language, setLanguage, t } = useLanguage()
  const { theme, toggleTheme } = useTheme()
  const [view, setView] = useState(() => (getInitialActiveSessionId() ? 'training' : 'sections'))
  const [sessionId, setSessionId] = useState(getInitialActiveSessionId)
  const [progressKey, setProgressKey] = useState(0)

  useEffect(() => {
    document.documentElement.setAttribute('data-accent', 'violet')
  }, [])

  useEffect(() => {
    if (user?.language && user.language !== language) setLanguage(user.language)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.language])

  if (authLoading) return <p className="app-loading">{t('common.loading')}</p>

  if (!token || !user) {
    return (
      <div className="auth-page">
        <LoginScreen />
      </div>
    )
  }

  function goToTraining(id) {
    setSessionId(id)
    localStorage.setItem(ACTIVE_SESSION_KEY, String(id))
    setView('training')
  }

  function goToSummary() {
    localStorage.removeItem(ACTIVE_SESSION_KEY)
    setView('summary')
  }

  function goToSections() {
    setSessionId(null)
    localStorage.removeItem(ACTIVE_SESSION_KEY)
    setView('sections')
  }

  function goToTrainForSection(sectionId) {
    try { localStorage.setItem(PRE_SELECT_SECTIONS_KEY, JSON.stringify([sectionId])) } catch {}
    navigate('start-training')
  }

  function goToTrainAgain({ selectedIds, mode, format, difficulty, count, sectionMode }) {
    try {
      localStorage.setItem(LAST_TRAINING_SETTINGS_KEY, JSON.stringify({ selectedIds, mode, format, difficulty, count, sectionMode }))
    } catch {}
    setSessionId(null)
    localStorage.removeItem(ACTIVE_SESSION_KEY)
    setView('start-training')
  }

  function navigate(target) {
    if (target === 'start-training' && sessionId) {
      setView('training')
    } else {
      if (target === 'progress') setProgressKey((k) => k + 1)
      setView(target)
    }
  }

  const activeNav = ['sections', 'progress', 'settings', 'question-bank'].includes(view)
    ? view
    : 'start-training'

  return (
    <div className="app-shell">
      <Sidebar activeNav={activeNav} onNavigate={navigate} user={user} onLogout={logout} />
      <div className="app-body">
        <AppHeader view={view} theme={theme} onToggleTheme={toggleTheme} />
        <main className="app-main">
          <div className="app-content">
            {view === 'sections' && <SectionsScreen />}
            {view === 'start-training' && (
              <StartTrainingScreen onStarted={goToTraining} onNavigate={navigate} />
            )}
            {view === 'training' && sessionId && (
              <TrainingScreen sessionId={sessionId} onFinish={goToSummary} onInterrupt={goToSections} />
            )}
            {view === 'summary' && sessionId && (
              <SummaryScreen sessionId={sessionId} onDone={goToSections} onTrainAgain={goToTrainAgain} />
            )}
            {view === 'progress' && <ProgressScreen key={progressKey} onTrainSection={goToTrainForSection} />}
            {view === 'settings' && <SettingsScreen />}
            {view === 'question-bank' && <QuestionBankScreen />}
          </div>
        </main>
      </div>
    </div>
  )
}

export default function App() {
  return (
    <LanguageProvider>
      <AuthProvider>
        <AppShell />
      </AuthProvider>
    </LanguageProvider>
  )
}
