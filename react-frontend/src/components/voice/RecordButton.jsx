import { forwardRef, useCallback, useImperativeHandle, useRef, useState } from 'react'
import './RecordButton.css'

/**
 * Props:
 *   mode               — 'toggle' (default) | 'hold'
 *   voiceControllerRef — React ref pointing at a VoiceController instance
 *   onRecordStart()    — optional; called when recording begins
 *   onRecordStop()     — optional; called when recording ends (before STT resolves)
 *   disabled           — bool
 *
 * Ref API (useImperativeHandle):
 *   activate()   — programmatically start recording (used by QuestionnaireForm
 *                  to auto-activate after TTS finishes)
 *   deactivate() — programmatically stop recording (used by silence-timeout)
 */
const RecordButton = forwardRef(function RecordButton({
  mode = 'toggle',
  voiceControllerRef,
  onRecordStart,
  onRecordStop,
  disabled = false,
}, ref) {
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

  // ── Imperative handle for parent-driven activation ──────────────────────────

  useImperativeHandle(
    ref,
    () => ({
      activate: () => {
        if (!disabled && !isRecording) handleStart()
      },
      deactivate: () => {
        if (isRecording) handleStop()
      },
    }),
    [disabled, isRecording, handleStart, handleStop],
  )

  // ── Toggle mode ──────────────────────────────────────────────────────────────

  const handleToggleClick = useCallback(() => {
    if (isRecording) handleStop()
    else handleStart()
  }, [isRecording, handleStart, handleStop])

  // ── Hold mode ────────────────────────────────────────────────────────────────

  const handlePointerDown = useCallback(
    (e) => {
      e.preventDefault() // prevent text selection / context menu on long-press
      // Capture the pointer so pointerup / pointercancel always fire on this
      // element even if the finger/cursor moves outside the button bounds.
      e.currentTarget.setPointerCapture(e.pointerId)
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
    // Fires after pointer capture is released (post-pointerup); holdActiveRef
    // will already be false in the normal case. Kept as a secondary safety net
    // for browsers that don't support setPointerCapture.
    if (holdActiveRef.current) {
      holdActiveRef.current = false
      handleStop()
    }
  }, [handleStop])

  // OS gesture interruptions, modal dialogs, and some browser actions fire
  // pointercancel instead of pointerup. Without this, holdActiveRef and
  // isRecording can be left permanently stuck in the recording state.
  const handlePointerCancel = useCallback(() => {
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
        onPointerCancel={handlePointerCancel}
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
})

export default RecordButton
