import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useServerWakeup } from './useServerWakeup'

describe('useServerWakeup', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('becomes ready without ever showing the banner when the backend responds quickly', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true }))
    const { result } = renderHook(() => useServerWakeup())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(result.current.ready).toBe(true)
    expect(result.current.waking).toBe(false)
  })

  it('shows the banner once the flash-delay grace period passes, then clears once the backend responds', async () => {
    let resolveFetch
    const fetchMock = vi.fn(() => new Promise((resolve) => { resolveFetch = resolve }))
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useServerWakeup())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(result.current.waking).toBe(false)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(400)
    })
    expect(result.current.waking).toBe(true)
    expect(result.current.ready).toBe(false)

    await act(async () => {
      resolveFetch({ ok: true })
      await vi.advanceTimersByTimeAsync(0)
    })

    expect(result.current.ready).toBe(true)
    expect(result.current.waking).toBe(false)
  })

  it('retries with backoff on failure and clears the banner once a retry succeeds', async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error('network error'))
      .mockResolvedValueOnce({ ok: true })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useServerWakeup())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(500)
    })
    expect(result.current.waking).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(result.current.ready).toBe(true)
    expect(result.current.waking).toBe(false)
  })

  it('stops auto-retrying after exhausting the bounded attempts, and retryNow starts a fresh check', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: false })
    vi.stubGlobal('fetch', fetchMock)

    const { result } = renderHook(() => useServerWakeup())

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000)
    })

    expect(result.current.exhausted).toBe(true)
    expect(result.current.ready).toBe(false)
    const attemptsSoFar = fetchMock.mock.calls.length

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60000)
    })
    expect(fetchMock.mock.calls.length).toBe(attemptsSoFar)

    fetchMock.mockResolvedValue({ ok: true })
    await act(async () => {
      result.current.retryNow()
      await vi.advanceTimersByTimeAsync(500)
    })

    expect(fetchMock.mock.calls.length).toBeGreaterThan(attemptsSoFar)
    expect(result.current.ready).toBe(true)
  })
})
