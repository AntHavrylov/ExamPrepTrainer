import { useEffect, useState } from 'react'

const THEME_KEY = 'prep_trainer_theme'
const START_THEME_KEY = 'ept_start_theme'

function getInitialTheme() {
  const pref = localStorage.getItem(START_THEME_KEY)
  if (pref === 'light' || pref === 'dark') return pref
  // 'auto' or nothing → follow system
  const stored = localStorage.getItem(THEME_KEY)
  if (!pref && (stored === 'light' || stored === 'dark')) return stored
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function getInitialStartTheme() {
  return localStorage.getItem(START_THEME_KEY) || 'auto'
}

export function useTheme() {
  const [theme, setThemeState] = useState(getInitialTheme)
  const [startTheme, setStartThemeState] = useState(getInitialStartTheme)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  function toggleTheme() {
    setThemeState((cur) => (cur === 'light' ? 'dark' : 'light'))
  }

  function setStartTheme(val) {
    localStorage.setItem(START_THEME_KEY, val)
    setStartThemeState(val)
    if (val === 'auto') {
      setThemeState(window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
    } else {
      setThemeState(val)
    }
  }

  return { theme, toggleTheme, startTheme, setStartTheme }
}
