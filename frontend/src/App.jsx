import { useEffect, useState } from 'react'
import './App.css'
import ThemeToggle from './components/ThemeToggle'
import Sidebar from './components/Sidebar'
import { ACTIVE_SESSION_KEY } from './api'
import { AuthProvider, useAuth } from './context/AuthContext'
import { LanguageProvider, useLanguage } from './context/LanguageContext'
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

function AppShell() {
  const { token, user, authLoading, logout } = useAuth()
  const { language, setLanguage, t } = useLanguage()
  const [view, setView] = useState(() => (getInitialActiveSessionId() ? 'training' : 'sections'))
  const [sessionId, setSessionId] = useState(getInitialActiveSessionId)

  useEffect(() => {
    if (user?.language && user.language !== language) setLanguage(user.language)
    // Only react to the account's language changing (e.g. after login/me);
    // setLanguage itself is stable and would otherwise cause a useless rerun.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.language])

  if (authLoading) return <p className="app-loading">{t('common.loading')}</p>

  if (!token || !user) {
    return (
      <div className="auth-page">
        <ThemeToggle />
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

  function navigate(target) {
    if (target === 'start-training' && sessionId) {
      // A session is still in progress - resume it instead of opening the
      // "start a new session" form, which would otherwise silently abandon it.
      setView('training')
    } else {
      // Just browsing another tab - leave any in-progress session intact so
      // "Train" can resume it later. Only an explicit Interrupt/Finish ends it.
      setView(target)
    }
  }

  const activeNav = ['sections', 'progress', 'settings', 'question-bank'].includes(view)
    ? view
    : 'start-training'

  return (
    <div className="app-shell">
      <Sidebar activeNav={activeNav} onNavigate={navigate} user={user} onLogout={logout} />

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
            <SummaryScreen sessionId={sessionId} onDone={goToSections} />
          )}
          {view === 'progress' && <ProgressScreen />}
          {view === 'settings' && <SettingsScreen />}
          {view === 'question-bank' && <QuestionBankScreen />}
        </div>
      </main>
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
