import { useCallback, useEffect, useRef, useState } from 'react'
import { checkHealth } from '../api'

// Give a same-region, already-warm backend a grace period to answer before
// showing anything — avoids flashing the banner on every normal page load.
const FLASH_DELAY_MS = 400

// Bounded backoff covering Azure App Service's typical ~20-30s cold start,
// then stop auto-retrying (no infinite hammering) and require a manual retry.
const RETRY_DELAYS_MS = [1000, 2000, 4000, 8000, 8000, 8000]

export function useServerWakeup() {
  const [ready, setReady] = useState(false)
  const [waking, setWaking] = useState(false)
  const [exhausted, setExhausted] = useState(false)
  const attemptIndexRef = useRef(0)
  const cancelledRef = useRef(false)

  const attempt = useCallback(async () => {
    const flashTimer = setTimeout(() => {
      if (!cancelledRef.current) setWaking(true)
    }, FLASH_DELAY_MS)

    const ok = await checkHealth()
    clearTimeout(flashTimer)
    if (cancelledRef.current) return

    if (ok) {
      setReady(true)
      setWaking(false)
      setExhausted(false)
      return
    }

    setWaking(true)
    const delay = RETRY_DELAYS_MS[attemptIndexRef.current]
    if (delay === undefined) {
      setExhausted(true)
      return
    }
    attemptIndexRef.current += 1
    setTimeout(() => {
      if (!cancelledRef.current) attempt()
    }, delay)
  }, [])

  useEffect(() => {
    cancelledRef.current = false
    attempt()
    return () => {
      cancelledRef.current = true
    }
  }, [attempt])

  const retryNow = useCallback(() => {
    attemptIndexRef.current = 0
    setExhausted(false)
    attempt()
  }, [attempt])

  return { ready, waking, exhausted, retryNow }
}
