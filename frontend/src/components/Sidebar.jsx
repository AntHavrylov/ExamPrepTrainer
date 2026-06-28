import { useLanguage } from '../context/LanguageContext'

const NAV_ITEMS = [
  { key: 'sections', labelKey: 'nav.sections', icon: IconBook },
  { key: 'start-training', labelKey: 'nav.train', icon: IconTarget },
  { key: 'question-bank', labelKey: 'nav.questionBank', icon: IconLayers },
  { key: 'progress', labelKey: 'nav.progress', icon: IconChart },
  { key: 'settings', labelKey: 'nav.settings', icon: IconSettings },
]

function IconBook() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5V5.5A2 2 0 0 1 6 3.5h12a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H6.5a2 2 0 0 0-2 2" />
      <path d="M4 19.5a2 2 0 0 1 2-2H19" />
    </svg>
  )
}

function IconTarget() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
      <circle cx="12" cy="12" r="0.5" fill="currentColor" />
    </svg>
  )
}

function IconLayers() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3l9 5-9 5-9-5 9-5Z" />
      <path d="M3 13l9 5 9-5" />
    </svg>
  )
}

function IconChart() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19V5" />
      <path d="M4 19h16" />
      <path d="M8 16v-4" />
      <path d="M12 16V8" />
      <path d="M16 16v-6" />
    </svg>
  )
}

function IconSettings() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1.08-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1.08 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9c.2.43.59.74 1.08 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  )
}

function IconLogout() {
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <path d="M16 17l5-5-5-5" />
      <path d="M21 12H9" />
    </svg>
  )
}

export default function Sidebar({ activeNav, onNavigate, user, onLogout }) {
  const { t } = useLanguage()
  const initials = (user.email || '?').slice(0, 2).toUpperCase()
  const displayName = (user.email || '').split('@')[0]

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-brand-mark">EP</span>
        <div className="sidebar-brand-text">
          <span className="sidebar-brand-name">ExamPrep</span>
          <span className="sidebar-brand-sub">Trainer</span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-nav-label">Workspace</div>
        {NAV_ITEMS.map(({ key, labelKey, icon: Icon }) => (
          <button
            key={key}
            type="button"
            className={`sidebar-nav-item${activeNav === key ? ' active' : ''}`}
            onClick={() => onNavigate(key)}
            title={t(labelKey)}
          >
            <Icon />
            <span>{t(labelKey)}</span>
            {activeNav === key && <span className="sidebar-nav-dot" aria-hidden="true" />}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div className="sidebar-user" title={user.email}>
          <span className="sidebar-user-avatar">{initials}</span>
          <div className="sidebar-user-info">
            <span className="sidebar-user-name">{displayName}</span>
            <span className="sidebar-user-email">{user.email}</span>
          </div>
        </div>

        <button type="button" className="sidebar-logout" onClick={onLogout} title={t('app.logout')}>
          <IconLogout />
          <span>{t('app.logout')}</span>
        </button>
      </div>
    </aside>
  )
}
