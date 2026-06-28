import { useEffect, useState } from 'react'

const ACCENT_KEY = 'ept_accent'
const DEPTH_KEY = 'ept_depth'

export const ACCENTS = ['violet', 'indigo', 'teal', 'rose']

const ACCENT_SWATCHES = {
  violet: '#7160c9',
  indigo: '#4f6ef0',
  teal:   '#0e9c8d',
  rose:   '#d54879',
}

export { ACCENT_SWATCHES }

export function useTweaks() {
  const [accent, setAccentState] = useState(() => localStorage.getItem(ACCENT_KEY) || 'violet')
  const [depth, setDepthState]   = useState(() => localStorage.getItem(DEPTH_KEY)  || 'depth')

  useEffect(() => {
    document.documentElement.setAttribute('data-accent', accent)
  }, [accent])

  useEffect(() => {
    document.documentElement.setAttribute('data-depth', depth)
  }, [depth])

  function setAccent(val) {
    localStorage.setItem(ACCENT_KEY, val)
    setAccentState(val)
  }

  function setDepth(val) {
    localStorage.setItem(DEPTH_KEY, val)
    setDepthState(val)
  }

  function reset() {
    setAccent('violet')
    setDepth('depth')
  }

  return { accent, setAccent, depth, setDepth, reset }
}
