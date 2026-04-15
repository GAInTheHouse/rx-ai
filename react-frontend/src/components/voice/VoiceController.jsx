import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from 'react'
import { startRecording, stopRecording } from '../../utils/audioUtils'

const API_BASE = 'http://localhost:8000'

/**
 * Headless controller (renders null) that owns the TTS playback pipeline and
 * the STT recording lifecycle. Expose an imperative API via a forwarded ref.
 *
 * Props:
 *   onTranscript(transcript, confidence) — called after a successful /stt round-trip
 *   onStatusChange(status)               — 'idle' | 'speaking' | 'listening'
 *   onError(err)                         — called on any failure; status resets to 'idle'
 *
 * Ref API (useImperativeHandle):
 *   speak(text)         → Promise<void>   — resolves when audio finishes playing
 *   startListening()    → Promise<void>   — acquires mic and starts recording
 *   stopListening()     → Promise<{ transcript, confidence }>
 *   getStatus()         → string          — current status without a re-render
 */
const VoiceController = forwardRef(function VoiceController(
  { onTranscript, onStatusChange, onError },
  ref,
) {
  const [status, setStatus] = useState('idle')
  const audioContextRef = useRef(null)
  const sourceNodeRef = useRef(null)

  // Keep a ref copy so imperative handlers always read the latest value
  // without needing status in their dependency arrays.
  const statusRef = useRef('idle')

  // Monotonically increasing token. Each speak() call claims a new token so
  // that async continuations and onended handlers from superseded calls can
  // detect they are stale and skip state updates.
  const playbackTokenRef = useRef(0)

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
   *
   * Race / clobber safety:
   *  - The playback token is incremented BEFORE the old source is stopped, so
   *    its onended handler sees a stale token and skips state updates.
   *  - Token checks after each await point bail out if a newer speak() won.
   */
  const speak = useCallback(
    async (text) => {
      // Claim a new token first — any prior speak()'s onended or async
      // continuation will see playbackTokenRef.current !== their captured token
      // and become no-ops.
      const token = ++playbackTokenRef.current

      // Detach the old source's onended handler BEFORE stopping it so the
      // handler cannot fire and clobber the new playback's state/refs.
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
        const res = await fetch(`${API_BASE}/tts`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text }),
        })

        if (!res.ok) throw new Error(`TTS request failed (${res.status})`)

        // A newer speak() may have started while this fetch was in flight
        if (playbackTokenRef.current !== token) return

        // Response is raw audio/mpeg bytes — not JSON
        const arrayBuffer = await res.arrayBuffer()
        const audioCtx = getAudioContext()

        // Browser autoplay policy may suspend the context; resume before decoding
        if (audioCtx.state === 'suspended') await audioCtx.resume()

        const audioBuffer = await audioCtx.decodeAudioData(arrayBuffer)

        // Check again after the potentially slow decode step
        if (playbackTokenRef.current !== token) return

        const source = audioCtx.createBufferSource()
        source.buffer = audioBuffer
        source.connect(audioCtx.destination)

        sourceNodeRef.current = source

        return new Promise((resolve) => {
          source.onended = () => {
            // Only update shared state if we are still the active playback
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
   * Acquire the microphone and start buffering audio chunks.
   * The RecordButton (or any parent) is responsible for calling stopListening().
   */
  const startListening = useCallback(async () => {
    updateStatus('listening')
    try {
      await startRecording()
    } catch (err) {
      updateStatus('idle')
      onError?.(err)
      throw err
    }
  }, [updateStatus, onError])

  /**
   * Stop the MediaRecorder, POST the blob to /stt, and return the transcript.
   * Also calls the onTranscript prop so parents don't have to await the return value.
   */
  const stopListening = useCallback(async () => {
    try {
      const blob = await stopRecording()
      updateStatus('idle')

      // Field name must be 'audio' — matches FastAPI: audio: UploadFile = File(...)
      const filename = blob.type.includes('mp4') ? 'recording.m4a' : 'recording.webm'
      const formData = new FormData()
      formData.append('audio', blob, filename)

      const res = await fetch(`${API_BASE}/stt`, {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) throw new Error(`STT request failed (${res.status})`)

      const { transcript, confidence } = await res.json()
      onTranscript?.(transcript, confidence)
      return { transcript, confidence }
    } catch (err) {
      updateStatus('idle')
      onError?.(err)
      throw err
    }
  }, [updateStatus, onTranscript, onError])

  useImperativeHandle(
    ref,
    () => ({
      speak,
      startListening,
      stopListening,
      getStatus: () => statusRef.current,
    }),
    [speak, startListening, stopListening],
  )

  return null
})

export default VoiceController
