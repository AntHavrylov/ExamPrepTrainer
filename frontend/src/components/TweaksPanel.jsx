import { useEffect, useRef } from 'react'
import { ACCENTS, ACCENT_SWATCHES } from '../hooks/useTweaks'

export default function TweaksPanel({
  open, onClose,
  accent, setAccent,
  depth,  setDepth,
  startTheme, setStartTheme,
  onReset,
}) {
  const panelRef = useRef(null)

  // Close on Escape or click outside
  useEffect(() => {
    if (!open) return

    function onKey(e) {
      if (e.key === 'Escape') onClose()
    }
    function onOutside(e) {
      if (panelRef.current && !panelRef.current.contains(e.target)) {
        // don't close if user clicked the trigger button itself (has data-tweaks-trigger)
        if (e.target.closest('[data-tweaks-trigger]')) return
        onClose()
      }
    }

    window.addEventListener('keydown', onKey)
    // delay so the opening click doesn't immediately close
    const t = setTimeout(() => document.addEventListener('mousedown', onOutside), 50)
    return () => {
      window.removeEventListener('keydown', onKey)
      clearTimeout(t)
      document.removeEventListener('mousedown', onOutside)
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="tweaks-panel" ref={panelRef} role="dialog" aria-modal="true" aria-label="Tweaks">
      <div className="tweaks-header">
        <span className="tweaks-title">Tweaks</span>
        <button type="button" className="tweaks-close" onClick={onClose} aria-label="Close">×</button>
      </div>

      <div className="tweaks-body">
        <div className="tweaks-section-label">Theme</div>

        {/* accent */}
        <div className="tweaks-row">
          <span className="tweaks-label">accent</span>
          <div className="tweaks-accent-row">
            {ACCENTS.map((a) => (
              <button
                key={a}
                type="button"
                className={`tweaks-swatch${accent === a ? ' active' : ''}`}
                style={{ '--swatch': ACCENT_SWATCHES[a] }}
                onClick={() => setAccent(a)}
                title={a}
                aria-pressed={accent === a}
              >
                {accent === a && (
                  <svg viewBox="0 0 12 12" width="10" height="10" fill="none" stroke="#fff" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M2 6l3 3 5-5" />
                  </svg>
                )}
              </button>
            ))}
            <span className="tweaks-accent-name">{accent}</span>
          </div>
        </div>

        {/* depth */}
        <div className="tweaks-row">
          <span className="tweaks-label">depth</span>
          <div className="tweaks-segment">
            {['depth', 'flat'].map((d) => (
              <button
                key={d}
                type="button"
                className={`tweaks-seg-btn${depth === d ? ' active' : ''}`}
                onClick={() => setDepth(d)}
              >
                {d}
              </button>
            ))}
          </div>
        </div>

        {/* startTheme */}
        <div className="tweaks-row">
          <span className="tweaks-label">startTheme</span>
          <div className="tweaks-segment">
            {['auto', 'light', 'dark'].map((t) => (
              <button
                key={t}
                type="button"
                className={`tweaks-seg-btn${startTheme === t ? ' active' : ''}`}
                onClick={() => setStartTheme(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="tweaks-footer">
        <button type="button" className="tweaks-reset-btn" onClick={onReset}>Reset</button>
        <button type="button" className="tweaks-save-btn" onClick={onClose}>Save as defaults</button>
      </div>
    </div>
  )
}
