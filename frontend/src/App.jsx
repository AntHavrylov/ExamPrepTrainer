import { useState } from 'react'
import './App.css'
import ThemeToggle from './components/ThemeToggle'
import Sidebar from './components/Sidebar'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginScreen from './screens/LoginScreen'
import SectionsScreen from './screens/SectionsScreen'
import StartTrainingScreen from './screens/StartTrainingScreen'
import TrainingScreen from './screens/TrainingScreen'
import SummaryScreen from './screens/SummaryScreen'
import ProgressScreen from './screens/ProgressScreen'
import SettingsScreen from './screens/SettingsScreen'

function AppShell() {
  const { token, user, authLoading, logout } = useAuth()
  const [view, setView] = useState('sections')
  const [sessionId, setSessionId] = useState(null)

  if (authLoading) return <p className="app-loading">Loading...</p>

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
    setView('training')
  }

  function goToSummary() {
    setView('summary')
  }

  function goToSections() {
    setSessionId(null)
    setView('sections')
  }

  function navigate(target) {
    if (target === 'sections') goToSections()
    else setView(target)
  }

  const activeNav =
    view === 'sections' || view === 'progress' || view === 'settings' ? view : 'start-training'

  return (
    <div className="app-shell">
      <Sidebar activeNav={activeNav} onNavigate={navigate} user={user} onLogout={logout} />

      <main className="app-main">
        <div className="app-content">
          {view === 'sections' && <SectionsScreen />}
          {view === 'start-training' && <StartTrainingScreen onStarted={goToTraining} />}
          {view === 'training' && sessionId && (
            <TrainingScreen sessionId={sessionId} onFinish={goToSummary} />
          )}
          {view === 'summary' && sessionId && (
            <SummaryScreen sessionId={sessionId} onDone={goToSections} />
          )}
          {view === 'progress' && <ProgressScreen />}
          {view === 'settings' && <SettingsScreen />}
        </div>
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <AppShell />
    </AuthProvider>
  )
}
