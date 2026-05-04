import { useCallback, useEffect, useRef, useState } from 'react'
import { pollJobs } from '../api'

interface UseJobPollingOptions {
  sessionId: string
  enabled: boolean       // only poll when there's an active session
  onJobsReady: () => void // called when unconsumed completed/failed jobs exist
}

interface UseJobPollingResult {
  hasPending: boolean
  hasUnconsumed: boolean
  checkNow: () => Promise<void>  // manual trigger after agent response
}

/**
 * Singleton poll loop for job status checking.
 * Only one interval runs at a time regardless of how many times checkNow() is called.
 *
 * State transitions:
 *  - checkNow() / interval tick returns has_pending=true          → start/keep polling every 60s
 *  - has_unconsumed=true                                          → call onJobsReady()
 *  - has_unconsumed=true  AND has_pending=false                   → stop polling
 *  - has_unconsumed=true  AND has_pending=true                    → keep polling
 *  - has_pending=false    AND has_unconsumed=false                → stop polling
 *  - sessionId changes                                            → reset + fresh check
 */
export function useJobPolling({
  sessionId,
  enabled,
  onJobsReady,
}: UseJobPollingOptions): UseJobPollingResult {
  const [hasPending, setHasPending] = useState(false)
  const [hasUnconsumed, setHasUnconsumed] = useState(false)

  // Refs for singleton management
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const isPollingRef = useRef(false)

  // notifiedRef: true after we've called onJobsReady for the current batch.
  // Resets when has_unconsumed goes false (agent processed jobs).
  const notifiedRef = useRef(false)

  // Keep stable refs to latest values so callbacks don't go stale
  const sessionIdRef = useRef(sessionId)
  const enabledRef = useRef(enabled)
  const onJobsReadyRef = useRef(onJobsReady)

  useEffect(() => { sessionIdRef.current = sessionId }, [sessionId])
  useEffect(() => { enabledRef.current = enabled }, [enabled])
  useEffect(() => { onJobsReadyRef.current = onJobsReady }, [onJobsReady])

  // ── Stop the running interval ──────────────────────────────────────────────
  const stopPolling = useCallback(() => {
    if (intervalRef.current !== null) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
    isPollingRef.current = false
  }, [])

  // ── Core result handler — shared by checkNow and the interval ──────────────
  const handleResult = useCallback(
    (result: { has_pending: boolean; has_unconsumed: boolean }) => {
      setHasPending(result.has_pending)
      setHasUnconsumed(result.has_unconsumed)

      if (result.has_unconsumed) {
        if (!notifiedRef.current) {
          notifiedRef.current = true
          onJobsReadyRef.current()
        }
        if (!result.has_pending) {
          // All done — nothing more to wait for
          stopPolling()
        }
        // has_pending=true: interval keeps running (already started)
      } else {
        // has_unconsumed is false: reset notification flag so a future batch triggers again
        notifiedRef.current = false
        if (!result.has_pending) {
          // Nothing going on — go idle
          stopPolling()
        }
        // has_pending=true but nothing unconsumed yet: keep polling
      }
    },
    [stopPolling],
  )

  // ── Start the 60s interval if not already running (singleton guard) ────────
  const startPollingIfNeeded = useCallback(() => {
    if (isPollingRef.current) return // already running
    isPollingRef.current = true
    intervalRef.current = setInterval(async () => {
      if (!enabledRef.current) return
      try {
        const result = await pollJobs(sessionIdRef.current)
        handleResult(result)
      } catch (err) {
        console.error('[useJobPolling] interval poll error:', err)
      }
    }, 60_000)
  }, [handleResult])

  // ── Manual trigger — call after every agent response ──────────────────────
  const checkNow = useCallback(async () => {
    if (!enabledRef.current) return
    try {
      const result = await pollJobs(sessionIdRef.current)
      handleResult(result)
      // If still pending after the immediate check, make sure the interval is running
      if (result.has_pending) {
        startPollingIfNeeded()
      }
    } catch (err) {
      console.error('[useJobPolling] checkNow error:', err)
    }
  }, [handleResult, startPollingIfNeeded])

  // ── React to session changes: reset state and run a fresh check ───────────
  useEffect(() => {
    stopPolling()
    setHasPending(false)
    setHasUnconsumed(false)
    notifiedRef.current = false

    if (enabled && sessionId) {
      // Kick off an immediate check without adding sessionId to deps
      // (using the ref ensures we use the latest value)
      checkNow()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, enabled])

  // ── Cleanup on unmount ─────────────────────────────────────────────────────
  useEffect(() => {
    return () => {
      stopPolling()
    }
  }, [stopPolling])

  return { hasPending, hasUnconsumed, checkNow }
}
