import { useCallback, useRef, useState } from 'react'
import './RecordButton.css'

/**
 * Props:
 *   mode               — 'toggle' (default) | 'hold'
 *   voiceControllerRef — React ref pointing at a VoiceController instance
 *   onRecordStart()    — optional; called when recording begins
 *   onRecordStop()     — optional; called when recording ends (before STT resolves)
 *   disabled           — bool
 */
function RecordButton({
  mode = 'toggle',
  voiceControllerRef,
  onRecordStart,
  onRecordStop,
  disabled = false,
}) {
  const [isRecording, setIsRecording] = useState(false)

  // Tracks whether a pointer-down initiated a hold session.
  // Guards against spurious onPointerUp / onPointerLeave after the gesture ends.
  const holdActiveRef = useRef(false)

  const handleStart = useCallback(async () => {
    if (disabled) return
    setIsRecording(true)
    onRecordStart?.()
    try {
      await voiceControllerRef.current?.startListening()
    } catch {
      // VoiceController already calls onError; just reset local state
      setIsRecording(false)
    }
  }, [disabled, voiceControllerRef, onRecordStart])

  const handleStop = useCallback(async () => {
    if (!isRecording) return
    setIsRecording(false)
    onRecordStop?.()
    try {
      await voiceControllerRef.current?.stopListening()
    } catch {
      // VoiceController already calls onError
    }
  }, [isRecording, voiceControllerRef, onRecordStop])

  // ── Toggle mode ──────────────────────────────────────────────────────────────

  const handleToggleClick = useCallback(() => {
    if (isRecording) handleStop()
    else handleStart()
  }, [isRecording, handleStart, handleStop])

  // ── Hold mode ────────────────────────────────────────────────────────────────

  const handlePointerDown = useCallback(
    (e) => {
      e.preventDefault() // prevent text selection / context menu on long-press
      holdActiveRef.current = true
      handleStart()
    },
    [handleStart],
  )

  const handlePointerUp = useCallback(() => {
    if (holdActiveRef.current) {
      holdActiveRef.current = false
      handleStop()
    }
  }, [handleStop])

  const handlePointerLeave = useCallback(() => {
    if (holdActiveRef.current) {
      holdActiveRef.current = false
      handleStop()
    }
  }, [handleStop])

  // ── Render ───────────────────────────────────────────────────────────────────

  if (mode === 'hold') {
    return (
      <button
        className={`record-button record-button--hold${isRecording ? ' record-button--active' : ''}`}
        onPointerDown={handlePointerDown}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerLeave}
        disabled={disabled}
        aria-label={isRecording ? 'Recording — release to stop' : 'Hold to record'}
        aria-pressed={isRecording}
        type="button"
      >
        <span className="record-button__icon" aria-hidden="true">
          {isRecording ? '⏹' : '🎤'}
        </span>
        <span className="record-button__label">
          {isRecording ? 'Recording…' : 'Hold to Record'}
        </span>
      </button>
    )
  }

  return (
    <button
      className={`record-button record-button--toggle${isRecording ? ' record-button--active' : ''}`}
      onClick={handleToggleClick}
      disabled={disabled}
      aria-label={isRecording ? 'Stop recording' : 'Start recording'}
      aria-pressed={isRecording}
      type="button"
    >
      <span className="record-button__icon" aria-hidden="true">
        {isRecording ? '⏹' : '🎤'}
      </span>
      <span className="record-button__label">
        {isRecording ? 'Tap to Stop' : 'Tap to Record'}
      </span>
    </button>
  )
}

export default RecordButton
