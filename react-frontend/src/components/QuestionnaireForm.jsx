import { useRef, useState } from 'react'
import PropTypes from 'prop-types'
import CameraCapture from './camera/CameraCapture'
import ImagePreview from './camera/ImagePreview'
import VoiceController from './voice/VoiceController'
import RecordButton from './voice/RecordButton'
import VoiceStatusBar from './voice/VoiceStatusBar'
import { requiresCamera, getCameraPrompt } from '../utils/cameraUtils'
import './QuestionnaireForm.css'

const API_BASE = 'http://localhost:8000'

function QuestionnaireForm({ questionnaire, onSubmit, onCancel, voiceMode }) {
  const [responses, setResponses] = useState({})
  const [errors, setErrors] = useState({})

  // Camera state — keyed by question.id
  const [cameraOpen, setCameraOpen] = useState(null)
  const [capturedImages, setCapturedImages] = useState({})
  const [imageDescriptions, setImageDescriptions] = useState({})
  const [isAnalyzing, setIsAnalyzing] = useState({})

  // Voice state
  const [voiceStatus, setVoiceStatus] = useState('idle')
  // Keyed by question.id so each RecordButton shows only its own error,
  // consistent with how capturedImages / imageDescriptions are scoped.
  const [voiceErrors, setVoiceErrors] = useState({})
  const voiceControllerRef = useRef(null)
  // Tracks which question's RecordButton most recently started recording.
  // A ref (not state) so the onTranscript closure always sees the current
  // value without needing to be recreated on every render.
  const activeQuestionIdRef = useRef(null)

  // ── Response helpers ────────────────────────────────────────────────

  const handleInputChange = (questionId, value) => {
    setResponses((prev) => ({ ...prev, [questionId]: value }))
    if (errors[questionId]) {
      setErrors((prev) => ({ ...prev, [questionId]: null }))
    }
  }

  const handleCheckboxChange = (questionId, option, checked) => {
    const current = responses[questionId] || []
    const next = checked ? [...current, option] : current.filter((v) => v !== option)
    handleInputChange(questionId, next)
  }

  // ── Camera helpers ──────────────────────────────────────────────────

  const handleOpenCamera = (questionId) => setCameraOpen(questionId)
  const handleCloseCamera = () => setCameraOpen(null)

  const handleCapture = async (questionId, question, base64) => {
    setCameraOpen(null)
    setCapturedImages((prev) => ({ ...prev, [questionId]: base64 }))
    setImageDescriptions((prev) => ({ ...prev, [questionId]: '' }))
    setIsAnalyzing((prev) => ({ ...prev, [questionId]: true }))

    try {
      const res = await fetch(`${API_BASE}/analyze-image`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image_base64: base64,
          question: question.question,
          question_id: question.id,
        }),
      })

      const data = res.ok ? await res.json() : { description: '' }
      const description = data.description || ''
      setImageDescriptions((prev) => ({ ...prev, [questionId]: description }))

      // Append description to current answer (after STT transcript if any)
      if (description) {
        setResponses((prev) => {
          const existing = (prev[questionId] || '').trim()
          const appended = existing
            ? `${existing}\n\n[Photo description: ${description}]`
            : `[Photo description: ${description}]`
          return { ...prev, [questionId]: appended }
        })
      }
    } catch {
      setImageDescriptions((prev) => ({ ...prev, [questionId]: '' }))
    } finally {
      setIsAnalyzing((prev) => ({ ...prev, [questionId]: false }))
    }
  }

  const handleRetakePhoto = (questionId) => {
    setCapturedImages((prev) => {
      const next = { ...prev }
      delete next[questionId]
      return next
    })
    setImageDescriptions((prev) => {
      const next = { ...prev }
      delete next[questionId]
      return next
    })
  }

  // ── Voice helpers ───────────────────────────────────────────────────

  const handleVoiceTranscript = (questionId, transcript) => {
    setResponses((prev) => {
      const existing = (prev[questionId] || '').trim()
      const next = existing ? `${existing} ${transcript}` : transcript
      return { ...prev, [questionId]: next }
    })
  }

  // ── Validation + submit ─────────────────────────────────────────────

  const validateForm = () => {
    const newErrors = {}
    questionnaire.questions.forEach((q) => {
      if (q.required) {
        const val = responses[q.id]
        if (!val || (Array.isArray(val) ? val.length === 0 : val.trim?.() === '')) {
          newErrors[q.id] = 'This question is required'
        }
      }
    })
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!validateForm()) {
      alert('Please answer all required questions before submitting.')
      return
    }
    const formattedResponses = {}
    questionnaire.questions.forEach((q) => {
      const answer = responses[q.id]
      if (answer !== undefined && answer !== null && answer !== '') {
        formattedResponses[q.question] = Array.isArray(answer)
          ? answer.join(', ')
          : answer.toString()
      }
    })
    onSubmit(questionnaire.id, responses, formattedResponses)
  }

  // ── Per-question camera section ─────────────────────────────────────

  const renderCameraSection = (question) => {
    const needsCamera =
      question.requires_image === true || requiresCamera(question.question)
    if (!needsCamera) return null

    const captured = capturedImages[question.id]
    const description = imageDescriptions[question.id]
    const analyzing = isAnalyzing[question.id]
    const prompt = question.image_prompt || getCameraPrompt(question.question)

    return (
      <div className="question-camera-section">
        {!captured ? (
          <button
            type="button"
            className="camera-trigger-btn"
            onClick={() => handleOpenCamera(question.id)}
            aria-label="Open camera to take a photo"
          >
            <span aria-hidden="true">📷</span> Take Photo
          </button>
        ) : (
          <ImagePreview
            base64={captured}
            description={description}
            isAnalyzing={analyzing}
            onRetake={() => handleRetakePhoto(question.id)}
          />
        )}
      </div>
    )
  }

  // ── Per-question voice section ──────────────────────────────────────

  const renderVoiceSection = (question) => {
    if (!voiceMode) return null
    return (
      <div className="question-voice-section">
        <VoiceStatusBar status={voiceStatus} />
        <RecordButton
          mode="toggle"
          voiceControllerRef={voiceControllerRef}
          onRecordStart={() => {
            activeQuestionIdRef.current = question.id
            setVoiceErrors((prev) => ({ ...prev, [question.id]: null }))
          }}
          disabled={voiceStatus === 'speaking'}
        />
        {voiceErrors[question.id] && (
          <p className="voice-error-msg">{voiceErrors[question.id]}</p>
        )}
        <p className="voice-hint">
          Tap to record your answer, then tap again to stop.
        </p>
      </div>
    )
  }

  // ── Question renderers ──────────────────────────────────────────────

  const renderQuestion = (question, index) => {
    const hasError = errors[question.id]

    const inputSection = (() => {
      switch (question.type) {
        case 'text':
          return (
            <input
              type="text"
              value={responses[question.id] || ''}
              onChange={(e) => handleInputChange(question.id, e.target.value)}
              className="question-input"
              placeholder="Type your answer…"
            />
          )

        case 'multiline':
          return (
            <textarea
              value={responses[question.id] || ''}
              onChange={(e) => handleInputChange(question.id, e.target.value)}
              className="question-textarea"
              placeholder="Type your answer…"
              rows={4}
            />
          )

        case 'scale':
          return (
            <>
              <div className="scale-container">
                <span className="scale-label">{question.min ?? 0}</span>
                <input
                  type="range"
                  min={question.min ?? 0}
                  max={question.max ?? 10}
                  value={responses[question.id] ?? question.min ?? 0}
                  onChange={(e) => handleInputChange(question.id, e.target.value)}
                  className="scale-input"
                />
                <span className="scale-label">{question.max ?? 10}</span>
              </div>
              <div className="scale-value">
                Current value:{' '}
                <strong>{responses[question.id] ?? question.min ?? 0}</strong>
              </div>
            </>
          )

        case 'radio':
          return (
            <div className="options-container">
              {(question.options || []).map((option) => (
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
          )

        case 'checkbox':
          return (
            <div className="options-container">
              {(question.options || []).map((option) => (
                <label key={option} className="checkbox-option">
                  <input
                    type="checkbox"
                    checked={(responses[question.id] || []).includes(option)}
                    onChange={(e) =>
                      handleCheckboxChange(question.id, option, e.target.checked)
                    }
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
          )

        default:
          return null
      }
    })()

    return (
      <div
        key={question.id}
        className={`question-block${hasError ? ' has-error' : ''}`}
      >
        <label className="question-label">
          {index + 1}. {question.question}
          {question.required && <span className="required">*</span>}
          {(question.requires_image || requiresCamera(question.question)) && (
            <span className="camera-badge" title="Photo may be requested">
              📷
            </span>
          )}
        </label>

        {inputSection}
        {renderCameraSection(question)}
        {renderVoiceSection(question)}

        {hasError && <span className="error-message">{hasError}</span>}
      </div>
    )
  }

  // ── Progress ────────────────────────────────────────────────────────

  const answeredCount = Object.keys(responses).filter((key) => {
    const val = responses[key]
    return val && (Array.isArray(val) ? val.length > 0 : val.toString().trim() !== '')
  }).length

  return (
    <div className="questionnaire-form-container">
      {/* Headless voice controller — wired to every RecordButton via ref */}
      {voiceMode && (
        <VoiceController
          ref={voiceControllerRef}
          onTranscript={(transcript) => {
            if (activeQuestionIdRef.current) {
              handleVoiceTranscript(activeQuestionIdRef.current, transcript)
            }
          }}
          onStatusChange={setVoiceStatus}
          onError={(err) => {
            if (activeQuestionIdRef.current) {
              setVoiceErrors((prev) => ({
                ...prev,
                [activeQuestionIdRef.current]: err.message,
              }))
            }
          }}
        />
      )}

      <div className="questionnaire-header">
        <h1>Patient Questionnaire</h1>
        <p className="questionnaire-meta">
          Visit: {questionnaire.visitId} | Released:{' '}
          {new Date(questionnaire.releasedAt).toLocaleDateString()}
        </p>
        {voiceMode && (
          <div className="voice-mode-active-banner">
            <VoiceStatusBar status={voiceStatus} />
            {voiceStatus === 'idle' && (
              <span className="voice-mode-label">Voice + Camera mode active</span>
            )}
          </div>
        )}
        <div className="progress-indicator">
          <span className="progress-text">
            Progress: {answeredCount} / {questionnaire.questions.length} questions
          </span>
          <div className="progress-bar">
            <div
              className="progress-fill"
              style={{
                width: `${(answeredCount / questionnaire.questions.length) * 100}%`,
              }}
            />
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="questionnaire-form">
        <div className="questions-list">
          {questionnaire.questions.map((q, i) => renderQuestion(q, i))}
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

      {/* Camera modal — rendered outside the form so it overlays everything */}
      {cameraOpen !== null && (() => {
        const q = questionnaire.questions.find((x) => x.id === cameraOpen)
        if (!q) return null
        const prompt = q.image_prompt || getCameraPrompt(q.question)
        return (
          <CameraCapture
            prompt={prompt}
            onCapture={(base64) => handleCapture(cameraOpen, q, base64)}
            onClose={handleCloseCamera}
          />
        )
      })()}
    </div>
  )
}

QuestionnaireForm.propTypes = {
  questionnaire: PropTypes.shape({
    id: PropTypes.string.isRequired,
    visitId: PropTypes.string,
    releasedAt: PropTypes.string,
    questions: PropTypes.arrayOf(
      PropTypes.shape({
        id: PropTypes.string.isRequired,
        question: PropTypes.string.isRequired,
        type: PropTypes.string,
        required: PropTypes.bool,
        options: PropTypes.arrayOf(PropTypes.string),
        requires_image: PropTypes.bool,
        image_prompt: PropTypes.string,
        min: PropTypes.number,
        max: PropTypes.number,
      }),
    ).isRequired,
  }).isRequired,
  onSubmit: PropTypes.func.isRequired,
  onCancel: PropTypes.func.isRequired,
  voiceMode: PropTypes.bool,
}

QuestionnaireForm.defaultProps = {
  voiceMode: false,
}

export default QuestionnaireForm
