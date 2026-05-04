import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from 'react'
import { startRecording, stopRecording } from '../../utils/audioUtils'

const API_BASE = 'http://localhost:8000'

/**
 * Headless controller (renders null) that owns the TTS playback pipeline and
 * the STT recording lifecycle. Expose an imperative API via a forwarded ref.
 *
 * Props:
 *   onTranscript(transcript, confidence, meta?) — called after a successful /stt round-trip
 *   onStatusChange(status)               — 'idle' | 'speaking' | 'listening'
 *   onError(err)                         — called on any failure; status resets to 'idle'
 *   silenceTimeoutMs                     — ms of recording before auto-stop (0 = disabled)
 *
 * Ref API (useImperativeHandle):
 *   speak(text)         → Promise<void>   — resolves when audio finishes playing
 *   startListening()    → Promise<void>   — acquires mic and starts recording
 *   stopListening()     → Promise<{ transcript, confidence }>
 *   cancelListening()   → void            — stops mic without POSTing to /stt
 *   resetSilenceTimer() → void            — while listening, restarts auto-stop delay (extend recording)
 *   getStatus()         → string          — current status without a re-render
 */
const VoiceController = forwardRef(function VoiceController(
  { onTranscript, onStatusChange, onError, silenceTimeoutMs = 0, workflowId = null },
  ref,
) {
  const [status, setStatus] = useState('idle')
  const audioContextRef = useRef(null)
  const sourceNodeRef = useRef(null)

  // Keep a ref copy so imperative handlers always read the latest value
  // without needing status in their dependency arrays.
  const statusRef = useRef('idle')

  // Monotonically increasing token — each speak() call claims a new token so
  // that stale async continuations can detect they are superseded.
  const playbackTokenRef = useRef(0)

  // Silence-timeout timer handle
  const silenceTimerRef = useRef(null)

  // Forward ref to stopListening so startListening can call it from the timer
  // without creating a circular useCallback dependency.
  const stopListeningRef = useRef(null)

  const updateStatus = useCallback(
    (next) => {
      statusRef.current = next
      setStatus(next)
      onStatusChange?.(next)
    },
    [onStatusChange],
  )

  /** Lazily create (or reuse) the singleton AudioContext. */
  const getAudioContext = useCallback(() => {
    if (!audioContextRef.current || audioContextRef.current.state === 'closed') {
      audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)()
    }
    return audioContextRef.current
  }, [])

  /**
   * Fetch /tts, decode the returned MP3 via AudioContext, and play it.
   * Cancels any audio that is currently playing before starting.
   * Resolves when playback ends naturally (or is superseded by a newer speak()).
   */
  const speak = useCallback(
    async (text) => {
      const token = ++playbackTokenRef.current

      // Detach old source's onended before stopping so it cannot clobber state.
      if (sourceNodeRef.current) {
        sourceNodeRef.current.onended = null
        try {
          sourceNodeRef.current.stop()
        } catch {
          // already stopped — ignore
        }
        sourceNodeRef.current = null
      }

      updateStatus('speaking')

      try {
        const headers = { 'Content-Type': 'application/json' }
        if (workflowId) headers['X-RxAI-Workflow-Id'] = workflowId
        const res = await fetch(`${API_BASE}/tts`, {
          method: 'POST',
          headers,
          body: JSON.stringify({ text }),
        })

        if (!res.ok) throw new Error(`TTS request failed (${res.status})`)

        if (playbackTokenRef.current !== token) return

        const arrayBuffer = await res.arrayBuffer()
        const audioCtx = getAudioContext()

        if (audioCtx.state === 'suspended') await audioCtx.resume()

        const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer)

        if (playbackTokenRef.current !== token) return

        const source = audioCtx.createBufferSource()
        source.buffer = audioBuffer
        source.connect(audioCtx.destination)
        sourceNodeRef.current = source

        return new Promise((resolve) => {
          source.onended = () => {
            if (playbackTokenRef.current === token) {
              sourceNodeRef.current = null
              updateStatus('idle')
            }
            resolve()
          }
          source.start()
        })
      } catch (err) {
        if (playbackTokenRef.current === token) {
          updateStatus('idle')
          onError?.(err)
        }
        throw err
      }
    },
    [getAudioContext, updateStatus, onError],
  )

  /**
   * Stop the MediaRecorder, POST the blob to /stt, and return the transcript.
   * Clears any active silence timer before proceeding.
   * Idempotent: returns immediately if not currently in the 'listening' state,
   * so the silence-timer path and the RecordButton path cannot double-execute.
   */
  const stopListening = useCallback(async () => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }

    if (statusRef.current !== 'listening') return

    try {
      const blob = await stopRecording()
      updateStatus('idle')

      const filename = blob.type.includes('mp4') ? 'recording.m4a' : 'recording.webm'
      const formData = new FormData()
      formData.append('audio', blob, filename)

      const res = await fetch(`${API_BASE}/stt`, {
        method: 'POST',
        headers: workflowId ? { 'X-RxAI-Workflow-Id': workflowId } : undefined,
        body: formData,
      })

      if (!res.ok) {
        let detail = ''
        try {
          const errJson = await res.json()
          detail = errJson?.detail ? String(errJson.detail) : JSON.stringify(errJson)
        } catch {
          try {
            detail = await res.text()
          } catch {
            detail = ''
          }
        }
        const suffix = detail ? `: ${detail}` : ''
        throw new Error(`STT request failed (${res.status})${suffix}`)
      }

      const data = await res.json()
      const { transcript, confidence, needs_rerecord, message, confidence_threshold } = data
      onTranscript?.(transcript, confidence, { needs_rerecord, message, confidence_threshold })
      return { transcript, confidence }
    } catch (err) {
      updateStatus('idle')
      onError?.(err)
      throw err
    }
  }, [updateStatus, onTranscript, onError, workflowId])

  // Keep the ref current so the silence timer can call the latest version.
  stopListeningRef.current = stopListening

  /**
   * Stop the active mic stream without sending audio to /stt.
   * Used when navigating away from a question mid-recording.
   */
  const cancelListening = useCallback(() => {
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    // stopRecording resolves a Blob; discard it
    stopRecording().catch(() => {})
    updateStatus('idle')
  }, [updateStatus])

  /**
   * Acquire the microphone and start buffering audio chunks.
   * If silenceTimeoutMs > 0, auto-calls stopListening() after that delay.
   */
  const armSilenceTimer = useCallback(() => {
    if (silenceTimeoutMs <= 0) return
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    if (statusRef.current !== 'listening') return
    silenceTimerRef.current = setTimeout(() => {
      silenceTimerRef.current = null
      stopListeningRef.current?.().catch(() => {})
    }, silenceTimeoutMs)
  }, [silenceTimeoutMs])

  const resetSilenceTimer = useCallback(() => {
    armSilenceTimer()
  }, [armSilenceTimer])

  const startListening = useCallback(async () => {
    updateStatus('listening')
    try {
      await startRecording()

      if (silenceTimeoutMs > 0) {
        armSilenceTimer()
      }
    } catch (err) {
      updateStatus('idle')

      // Translate the opaque NotAllowedError into something user-friendly.
      const friendly =
        err.name === 'NotAllowedError'
          ? new Error('Microphone access was denied. Please allow microphone permissions and try again.')
          : err

      onError?.(friendly)
      throw friendly
    }
  }, [updateStatus, onError, silenceTimeoutMs, armSilenceTimer])

  useImperativeHandle(
    ref,
    () => ({
      speak,
      startListening,
      stopListening,
      cancelListening,
      resetSilenceTimer,
      getStatus: () => statusRef.current,
    }),
    [speak, startListening, stopListening, cancelListening, resetSilenceTimer],
  )

  return null
})

export default VoiceController
