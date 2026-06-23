import { useState } from 'react'
import './App.css'
import ThemeToggle from './components/ThemeToggle'
import { AuthProvider, useAuth } from './context/AuthContext'
import LoginScreen from './screens/LoginScreen'
import SectionsScreen from './screens/SectionsScreen'
import StartTrainingScreen from './screens/StartTrainingScreen'
import TrainingScreen from './screens/TrainingScreen'
import SummaryScreen from './screens/SummaryScreen'
import ProgressScreen from './screens/ProgressScreen'

function AppShell() {
  const { token, user, authLoading, logout } = useAuth()
  const [view, setView] = useState('sections')
  const [sessionId, setSessionId] = useState(null)

  if (authLoading) return <p>Loading...</p>

  if (!token || !user) {
    return <LoginScreen />
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

  return (
    <div className="app">
      <header className="app-header">
        <h1>Exam Prep Trainer</h1>
        <div className="app-header-right">
          <span>{user.email}</span>
          <button onClick={logout}>Log out</button>
        </div>
      </header>

      <nav className="app-nav">
        <button onClick={goToSections} disabled={view === 'sections'}>
          Sections
        </button>
        <button onClick={() => setView('start-training')} disabled={view === 'start-training'}>
          Train
        </button>
        <button onClick={() => setView('progress')} disabled={view === 'progress'}>
          Progress
        </button>
      </nav>

      <main>
        {view === 'sections' && <SectionsScreen />}
        {view === 'start-training' && <StartTrainingScreen onStarted={goToTraining} />}
        {view === 'training' && sessionId && (
          <TrainingScreen sessionId={sessionId} onFinish={goToSummary} />
        )}
        {view === 'summary' && sessionId && (
          <SummaryScreen sessionId={sessionId} onDone={goToSections} />
        )}
        {view === 'progress' && <ProgressScreen />}
      </main>
    </div>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <ThemeToggle />
      <AppShell />
    </AuthProvider>
  )
}
