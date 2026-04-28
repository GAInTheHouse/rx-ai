import { useCallback, useEffect, useRef, useState } from 'react'
import VoiceController from './voice/VoiceController'
import RecordButton from './voice/RecordButton'
import VoiceStatusBar from './voice/VoiceStatusBar'
import './QuestionnaireForm.css'

// How long (ms) to wait after TTS ends before auto-activating the mic.
const TTS_TO_MIC_DELAY_MS = 400
// Silence auto-stop timeout passed down to VoiceController.
const SILENCE_TIMEOUT_MS = 3000

/**
 * QuestionnaireForm
 *
 * Props:
 *   questionnaire  — { id, visitId, releasedAt, questions: Question[] }
 *   voiceMode      — bool  (default false) — step-by-step voice wizard
 *   onSubmit(id, responses, formattedResponses)
 *   onCancel()
 */
function QuestionnaireForm({ questionnaire, onSubmit, onCancel, voiceMode = false }) {
  const [responses, setResponses] = useState({})
  const [errors, setErrors] = useState({})

  // ── Voice mode state ────────────────────────────────────────────────────────
  const [voiceStatus, setVoiceStatus] = useState('idle')
  const [voiceError, setVoiceError] = useState(null)
  const [currentStep, setCurrentStep] = useState(0)
  const [lastTranscript, setLastTranscript] = useState(null)
  const [lastTranscriptConfidence, setLastTranscriptConfidence] = useState(null)
  // Countdown seconds shown in VoiceStatusBar while recording
  const [silenceCountdown, setSilenceCountdown] = useState(null)
  // Set of question indices already spoken in this session (avoids re-speak on re-render)
  const spokenStepsRef = useRef(new Set())

  const voiceControllerRef = useRef(null)
  const recordButtonRef = useRef(null)
  const prevVoiceStatusRef = useRef('idle')
  const countdownTimerRef = useRef(null)

  const questions = questionnaire.questions ?? []
  const totalSteps = questions.length
  const currentQuestionForVoice = voiceMode ? questions[currentStep] : null
  const sttEnabledForCurrentStep =
    !!currentQuestionForVoice &&
    (currentQuestionForVoice.type === 'text' || currentQuestionForVoice.type === 'multiline')

  // ── Shared helpers ──────────────────────────────────────────────────────────

  const handleInputChange = (questionId, value) => {
    setResponses((prev) => ({ ...prev, [questionId]: value }))
    if (errors[questionId]) {
      setErrors((prev) => ({ ...prev, [questionId]: null }))
    }
  }

  const handleCheckboxChange = (questionId, option, checked) => {
    const currentValues = responses[questionId] || []
    const newValues = checked
      ? [...currentValues, option]
      : currentValues.filter((v) => v !== option)
    setResponses((prev) => ({ ...prev, [questionId]: newValues }))
    if (errors[questionId]) {
      setErrors((prev) => ({ ...prev, [questionId]: null }))
    }
  }

  // ── Validation + submit ─────────────────────────────────────────────────────

  const validateForm = () => {
    const newErrors = {}
    questions.forEach((q) => {
      if (q.required) {
        const response = responses[q.id]
        if (!response || (Array.isArray(response) && response.length === 0) || response.trim?.() === '') {
          newErrors[q.id] = 'This question is required'
        }
      }
    })
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e) => {
    e?.preventDefault()
    if (!validateForm()) {
      alert('Please answer all required questions before submitting.')
      return
    }
    const formattedResponses = {}
    questions.forEach((q) => {
      const answer = responses[q.id]
      if (answer !== undefined && answer !== null && answer !== '') {
        formattedResponses[q.question] = Array.isArray(answer)
          ? answer.join(', ')
          : answer.toString()
      }
    })
    onSubmit(questionnaire.id, responses, formattedResponses)
  }

  // ── Voice mode: auto-speak on step change ───────────────────────────────────

  useEffect(() => {
    if (!voiceMode) return
    if (currentStep >= totalSteps) return
    if (spokenStepsRef.current.has(currentStep)) return

    const q = questions[currentStep]
    if (!q) return

    spokenStepsRef.current.add(currentStep)

    // Cancel any mic session from the previous step before speaking the new one
    if (voiceControllerRef.current?.getStatus() === 'listening') {
      voiceControllerRef.current.cancelListening()
    }

    voiceControllerRef.current?.speak(q.question).catch((err) => {
      setVoiceError(err.message)
    })
  }, [voiceMode, currentStep, totalSteps, questions])

  // ── Voice mode: detect speaking→idle transition and auto-activate mic ────────

  const handleVoiceStatusChange = useCallback((newStatus) => {
    const prev = prevVoiceStatusRef.current
    prevVoiceStatusRef.current = newStatus
    setVoiceStatus(newStatus)

    // TTS just ended → auto-start recording after a short pause
    if (prev === 'speaking' && newStatus === 'idle') {
      setTimeout(() => {
        if (sttEnabledForCurrentStep) {
          recordButtonRef.current?.activate()
        }
      }, TTS_TO_MIC_DELAY_MS)
    }

    // Silence timer auto-stopped the mic → sync RecordButton's local isRecording.
    // deactivate() resets its UI and calls stopListening(), which returns early
    // via the idempotent guard since status is already 'idle' at this point.
    if (prev === 'listening' && newStatus === 'idle') {
      recordButtonRef.current?.deactivate()
    }

    // Recording started → begin countdown display
    if (newStatus === 'listening') {
      let secs = Math.round(SILENCE_TIMEOUT_MS / 1000)
      setSilenceCountdown(secs)
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
      countdownTimerRef.current = setInterval(() => {
        secs -= 1
        if (secs <= 0) {
          clearInterval(countdownTimerRef.current)
          countdownTimerRef.current = null
          setSilenceCountdown(null)
        } else {
          setSilenceCountdown(secs)
        }
      }, 1000)
    }

    // Recording stopped → clear countdown
    if (prev === 'listening' && newStatus === 'idle') {
      if (countdownTimerRef.current) {
        clearInterval(countdownTimerRef.current)
        countdownTimerRef.current = null
      }
      setSilenceCountdown(null)
    }
  }, [sttEnabledForCurrentStep])

  // ── Voice mode: STT result → fill answer field ───────────────────────────────

  const handleTranscript = useCallback((transcript, confidence, meta) => {
    if (currentStep >= totalSteps) return
    const q = questions[currentStep]
    if (!q) return

    // Only surface transcript when the current question supports free-text answers.
    if (!(q.type === 'text' || q.type === 'multiline')) return

    setLastTranscript(transcript || '')
    setLastTranscriptConfidence(confidence ?? null)

    if (meta?.needs_rerecord) {
      setVoiceError(meta.message || 'Low transcription confidence. Please re-record your answer.')
    }

    // Auto-fill free-text answers from the transcript.
    // For select / checkbox / scale questions the patient must use the input
    // controls directly — mapping raw speech to a discrete option reliably
    // would require fuzzy matching or a dedicated NLU step.
    if (q.type === 'text' || q.type === 'multiline') {
      setResponses((prev) => ({ ...prev, [q.id]: transcript }))
    }
    // Clear any stale error for this question
    setErrors((prev) => ({ ...prev, [q.id]: null }))
  }, [currentStep, totalSteps, questions])

  // ── Voice mode: errors ───────────────────────────────────────────────────────

  const handleVoiceError = useCallback((err) => {
    setVoiceError(err.message)
  }, [])

  // Dismiss error and let the patient retry manually
  const dismissError = () => setVoiceError(null)

  // ── Voice step navigation ────────────────────────────────────────────────────

  const goToStep = (nextStep) => {
    // Cancel any in-flight recording when navigating
    if (voiceControllerRef.current?.getStatus() === 'listening') {
      voiceControllerRef.current.cancelListening()
    }
    setVoiceError(null)
    setLastTranscript(null)
    setLastTranscriptConfidence(null)
    setCurrentStep(nextStep)
  }

  // ── Cleanup on unmount ───────────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
      if (voiceControllerRef.current?.getStatus() === 'listening') {
        voiceControllerRef.current.cancelListening()
      }
    }
  }, [])

  // ── Question renderers ───────────────────────────────────────────────────────

  const renderQuestionInput = (question) => {
    const hasError = errors[question.id]

    switch (question.type) {
      case 'text':
        return (
          <>
            <input
              type="text"
              value={responses[question.id] || ''}
              onChange={(e) => handleInputChange(question.id, e.target.value)}
              className="question-input"
              placeholder="Type your answer or use the mic…"
              aria-label={question.question}
            />
            {hasError && <span className="error-message" role="alert">{hasError}</span>}
          </>
        )

      case 'multiline':
        return (
          <>
            <textarea
              value={responses[question.id] || ''}
              onChange={(e) => handleInputChange(question.id, e.target.value)}
              className="question-textarea"
              placeholder="Type your answer or use the mic…"
              rows={4}
              aria-label={question.question}
            />
            {hasError && <span className="error-message" role="alert">{hasError}</span>}
          </>
        )

      case 'scale':
        return (
          <>
            <div className="scale-container">
              <span className="scale-label">{question.min}</span>
              <input
                type="range"
                min={question.min}
                max={question.max}
                value={responses[question.id] || question.min}
                onChange={(e) => handleInputChange(question.id, e.target.value)}
                className="scale-input"
                aria-label={`${question.question} — value ${responses[question.id] || question.min}`}
              />
              <span className="scale-label">{question.max}</span>
            </div>
            <div className="scale-value">
              Current value: <strong>{responses[question.id] || question.min}</strong>
            </div>
            {hasError && <span className="error-message" role="alert">{hasError}</span>}
          </>
        )

      case 'radio':
        return (
          <>
            <div className="options-container" role="radiogroup" aria-label={question.question}>
              {question.options.map((option) => (
                <label key={option} className="radio-option">
                  <input
                    type="radio"
                    name={question.id}
                    value={option}
                    checked={responses[question.id] === option}
                    onChange={(e) => handleInputChange(question.id, e.target.value)}
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
            {hasError && <span className="error-message" role="alert">{hasError}</span>}
          </>
        )

      case 'checkbox':
        return (
          <>
            <div className="options-container">
              {question.options.map((option) => (
                <label key={option} className="checkbox-option">
                  <input
                    type="checkbox"
                    checked={(responses[question.id] || []).includes(option)}
                    onChange={(e) => handleCheckboxChange(question.id, option, e.target.checked)}
                    aria-label={option}
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
            {hasError && <span className="error-message" role="alert">{hasError}</span>}
          </>
        )

      default:
        return null
    }
  }

  // ── Standard (text-only) form ────────────────────────────────────────────────

  if (!voiceMode) {
    const answeredCount = Object.keys(responses).filter((key) => {
      const value = responses[key]
      return value && (Array.isArray(value) ? value.length > 0 : value.trim() !== '')
    }).length

    return (
      <div className="questionnaire-form-container">
        <div className="questionnaire-header">
          <h1>Patient Questionnaire</h1>
          <p className="questionnaire-meta">
            Visit: {questionnaire.visitId} | Released:{' '}
            {new Date(questionnaire.releasedAt).toLocaleDateString()}
          </p>
          <div className="progress-indicator">
            <span className="progress-text">
              Progress: {answeredCount} / {questions.length} questions
            </span>
            <div className="progress-bar">
              <div
                className="progress-fill"
                style={{ width: `${questions.length > 0 ? (answeredCount / questions.length) * 100 : 0}%` }}
              />
            </div>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="questionnaire-form">
          <div className="questions-list">
            {questions.map((question, index) => {
              const hasError = errors[question.id]
              return (
                <div
                  key={question.id}
                  className={`question-block ${hasError ? 'has-error' : ''}`}
                >
                  <label className="question-label">
                    {index + 1}. {question.question}
                    {question.required && <span className="required">*</span>}
                  </label>
                  {renderQuestionInput(question)}
                </div>
              )
            })}
          </div>

          <div className="form-actions">
            <button type="button" onClick={onCancel} className="cancel-button">
              Cancel
            </button>
            <button type="submit" className="submit-button">
              Submit Questionnaire
            </button>
          </div>
        </form>
      </div>
    )
  }

  // ── Voice mode — step-by-step wizard ─────────────────────────────────────────

  const currentQuestion = questions[currentStep]
  const isLastStep = currentStep === totalSteps - 1
  const currentAnswer = currentQuestion ? responses[currentQuestion.id] : undefined
  const hasCurrentAnswer =
    currentAnswer !== undefined &&
    currentAnswer !== null &&
    (Array.isArray(currentAnswer) ? currentAnswer.length > 0 : currentAnswer.toString().trim() !== '')

  const progressPct = totalSteps > 0 ? ((currentStep + 1) / totalSteps) * 100 : 0

  return (
    <div className="questionnaire-form-container qf--voice">
      {/* Hidden headless voice engine */}
      <VoiceController
        ref={voiceControllerRef}
        onTranscript={handleTranscript}
        onStatusChange={handleVoiceStatusChange}
        onError={handleVoiceError}
        silenceTimeoutMs={SILENCE_TIMEOUT_MS}
      />

      {/* Header */}
      <div className="questionnaire-header">
        <h1>Patient Questionnaire</h1>
        <p className="questionnaire-meta">
          Visit: {questionnaire.visitId} | Released:{' '}
          {new Date(questionnaire.releasedAt).toLocaleDateString()}
        </p>
        <div className="progress-indicator">
          <span className="progress-text">
            Question {currentStep + 1} of {totalSteps}
          </span>
          <div className="progress-bar">
            <div className="progress-fill" style={{ width: `${progressPct}%` }} />
          </div>
        </div>
      </div>

      {/* Voice Status Bar */}
      <div className="voice-status-row">
        <VoiceStatusBar
          status={voiceStatus}
          error={voiceError}
          silenceCountdown={voiceStatus === 'listening' ? silenceCountdown : null}
        />
        {voiceError && (
          <button className="voice-error-dismiss" onClick={dismissError} type="button">
            Dismiss
          </button>
        )}
      </div>

      {sttEnabledForCurrentStep && lastTranscript != null && (
        <div className="voice-transcript-preview" role="status" aria-live="polite">
          <div className="voice-transcript-preview__header">
            <span className="voice-transcript-preview__title">Last transcript</span>
            {lastTranscriptConfidence != null && (
              <span className="voice-transcript-preview__confidence">
                Confidence: {Number(lastTranscriptConfidence).toFixed(2)}
              </span>
            )}
          </div>
          <p className="voice-transcript-preview__text">
            {lastTranscript.trim() ? lastTranscript : '(empty)'}
          </p>
        </div>
      )}

      {/* Active question card */}
      {currentQuestion && (
        <div
          className={`questionnaire-form voice-step-card ${
            errors[currentQuestion.id] ? 'has-error' : ''
          }`}
        >
          <div className="voice-step-header">
            <span className="voice-step-counter">
              {currentStep + 1} / {totalSteps}
            </span>
            {currentQuestion.required && (
              <span className="required voice-required-badge">Required</span>
            )}
          </div>

          <p className="voice-question-text">{currentQuestion.question}</p>

          {/* Answer input (editable transcript for text/multiline; standard controls for others) */}
          <div className="voice-answer-area">
            {renderQuestionInput(currentQuestion)}
          </div>

          {/* Recording controls */}
          <div className="voice-controls">
            <RecordButton
              ref={recordButtonRef}
              mode="toggle"
              voiceControllerRef={voiceControllerRef}
              disabled={voiceStatus === 'speaking' || !sttEnabledForCurrentStep}
              ariaLabel={
                !sttEnabledForCurrentStep
                  ? 'Voice transcription is disabled for this question'
                  : voiceStatus === 'listening'
                    ? 'Stop recording and transcribe'
                    : 'Start recording your answer'
              }
            />

            <button
              type="button"
              className="voice-repeat-btn"
              onClick={() => {
                // Allow re-speaking the current question
                spokenStepsRef.current.delete(currentStep)
                voiceControllerRef.current?.speak(currentQuestion.question).catch((err) =>
                  setVoiceError(err.message),
                )
              }}
              disabled={voiceStatus !== 'idle'}
              aria-label="Repeat question"
              title="Repeat question"
            >
              🔁 Repeat
            </button>
          </div>

          {/* Editable transcript hint */}
          {(currentQuestion.type === 'text' || currentQuestion.type === 'multiline') && (
            <p className="voice-transcript-hint">
              The mic fills the field above — you can edit it before moving on.
            </p>
          )}
        </div>
      )}

      {/* Navigation */}
      <div className="voice-nav">
        <button
          type="button"
          className="cancel-button"
          onClick={onCancel}
        >
          Cancel
        </button>

        {currentStep > 0 && (
          <button
            type="button"
            className="voice-back-btn"
            onClick={() => goToStep(currentStep - 1)}
            disabled={voiceStatus === 'speaking' || voiceStatus === 'listening'}
          >
            ← Back
          </button>
        )}

        {!isLastStep ? (
          <button
            type="button"
            className="voice-next-btn"
            onClick={() => goToStep(currentStep + 1)}
            disabled={
              voiceStatus === 'speaking' ||
              voiceStatus === 'listening' ||
              (currentQuestion?.required && !hasCurrentAnswer)
            }
          >
            Next →
          </button>
        ) : (
          <button
            type="button"
            className="submit-button"
            onClick={handleSubmit}
            disabled={
              voiceStatus === 'speaking' ||
              voiceStatus === 'listening' ||
              (currentQuestion?.required && !hasCurrentAnswer)
            }
          >
            Submit Questionnaire
          </button>
        )}
      </div>
    </div>
  )
}

export default QuestionnaireForm
