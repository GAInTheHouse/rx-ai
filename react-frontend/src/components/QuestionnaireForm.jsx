import { useCallback, useEffect, useRef, useState } from 'react'
import CameraCapture from './camera/CameraCapture'
import VoiceController from './voice/VoiceController'
import RecordButton from './voice/RecordButton'
import VoiceStatusBar from './voice/VoiceStatusBar'
import './QuestionnaireForm.css'

const API_BASE = 'http://localhost:8000'
const MAX_PHOTOS_PER_QUESTION = 6

// How long (ms) to wait after TTS ends before auto-activating the mic.
const TTS_TO_MIC_DELAY_MS = 400
// Silence auto-stop timeout passed down to VoiceController.
const SILENCE_TIMEOUT_MS = 5000

/**
 * Resolve min/max for scale questions. Missing attrs make <input type="range"> default to 0–100
 * in browsers; we infer "0 to 10" (etc.) from the question text when needed.
 */
function getScaleBounds(question) {
  const qtext = `${question?.question || ''} ${question?.rationale || ''}`
  let min = Number(question?.min)
  let max = Number(question?.max)

  const textRange = qtext.match(/\b(\d{1,3})\s*(?:to|-|–)\s*(\d{1,3})\b/i)
  let inferred = null
  if (textRange) {
    const a = parseInt(textRange[1], 10)
    const b = parseInt(textRange[2], 10)
    if (!Number.isNaN(a) && !Number.isNaN(b)) {
      inferred = { min: Math.min(a, b), max: Math.max(a, b) }
    }
  }

  if (inferred) {
    if (!Number.isFinite(min)) min = inferred.min
    if (!Number.isFinite(max)) max = inferred.max
    if (Number.isFinite(max) && max === 100 && inferred.max <= 10) {
      min = inferred.min
      max = inferred.max
    }
  }

  if (!Number.isFinite(min)) min = 0
  if (!Number.isFinite(max)) max = 10
  if (max <= min) max = min + 10
  return { min, max }
}

function parseSpokenScaleValue(transcript, min, max) {
  const lo = Number(min)
  const hi = Number(max)
  const low = Number.isFinite(lo) ? lo : 0
  const high = Number.isFinite(hi) ? hi : 10
  const t = (transcript || '').toLowerCase().trim()
  const words = {
    zero: 0,
    one: 1,
    two: 2,
    three: 3,
    four: 4,
    five: 5,
    six: 6,
    seven: 7,
    eight: 8,
    nine: 9,
    ten: 10,
  }
  for (const [w, v] of Object.entries(words)) {
    const re = new RegExp(`\\b${w}\\b`)
    if (re.test(t) && v >= low && v <= high) return String(v)
  }

  const outOfMatches = [...t.matchAll(/(\d{1,3})\s*out\s*of\s*(\d{1,3})/gi)]
  for (let i = outOfMatches.length - 1; i >= 0; i--) {
    const num = parseInt(outOfMatches[i][1], 10)
    const denom = parseInt(outOfMatches[i][2], 10)
    if (Number.isNaN(num) || Number.isNaN(denom) || denom === 0) continue
    if (denom === 10 && num >= low && num <= high) return String(num)
    if (denom === 100 && high - low === 10 && num >= 0 && num <= 100) {
      const mapped = Math.round((num / 100) * (high - low) + low)
      if (mapped >= low && mapped <= high) return String(mapped)
    }
  }

  const nums = [...t.matchAll(/\b(\d{1,3})\b/g)]
    .map((m) => parseInt(m[1], 10))
    .filter((n) => !Number.isNaN(n))
  for (let i = nums.length - 1; i >= 0; i--) {
    const v = nums[i]
    if (v >= low && v <= high) return String(v)
  }

  if (high - low === 10 && low === 0) {
    for (let i = nums.length - 1; i >= 0; i--) {
      const v = nums[i]
      if (v > high && v <= 100) {
        const mapped = Math.round(v / 10)
        if (mapped >= low && mapped <= high) return String(mapped)
      }
    }
  }

  return null
}

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
  /** Per question: uploaded/captured image(s) with clinical summary from /analyze-image */
  const [photoByQuestion, setPhotoByQuestion] = useState({})
  /** Optional questions the patient chose to skip (no answer required). */
  const [skippedQuestions, setSkippedQuestions] = useState({})
  const [cameraQuestionId, setCameraQuestionId] = useState(null)
  const [cameraBusy, setCameraBusy] = useState(false)
  const [cameraError, setCameraError] = useState(null)

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
  const photoFileInputRef = useRef(null)
  const uploadTargetQuestionIdRef = useRef(null)
  const prevVoiceStatusRef = useRef('idle')
  const countdownTimerRef = useRef(null)
  const silenceDeadlineRef = useRef(0)
  const workflowIdRef = useRef(null)
  const photoByQuestionRef = useRef({})

  useEffect(() => {
    photoByQuestionRef.current = photoByQuestion
  }, [photoByQuestion])

  const questions = questionnaire.questions ?? []
  const totalSteps = questions.length
  const currentQuestionForVoice = voiceMode ? questions[currentStep] : null

  useEffect(() => {
    try {
      workflowIdRef.current = crypto.randomUUID()
    } catch {
      workflowIdRef.current = `${Date.now()}-${Math.random().toString(16).slice(2)}`
    }
  }, [questionnaire?.id])

  const sttEnabledForCurrentStep =
    !!currentQuestionForVoice &&
    (currentQuestionForVoice.type === 'text' ||
      currentQuestionForVoice.type === 'multiline' ||
      currentQuestionForVoice.type === 'scale')

  // ── Shared helpers ──────────────────────────────────────────────────────────

  const handleInputChange = (questionId, value) => {
    setSkippedQuestions((prev) => {
      if (!prev[questionId]) return prev
      const { [questionId]: _, ...rest } = prev
      return rest
    })
    setResponses((prev) => ({ ...prev, [questionId]: value }))
    if (errors[questionId]) {
      setErrors((prev) => ({ ...prev, [questionId]: null }))
    }
  }

  const removePhotoShot = useCallback((questionId, index) => {
    setPhotoByQuestion((prev) => {
      const cur = prev[questionId]
      if (!cur?.images?.length) return prev
      const nextImages = cur.images.filter((_, i) => i !== index)
      if (nextImages.length === 0) {
        const { [questionId]: _, ...rest } = prev
        return rest
      }
      return { ...prev, [questionId]: { images: nextImages } }
    })
  }, [])

  /** Patient-approved insert of vision summary into the free-text answer field. */
  const insertPhotoSummaryIntoAnswer = useCallback((questionId, description) => {
    const text = (description || '').trim()
    if (!text) return
    setSkippedQuestions((prev) => {
      if (!prev[questionId]) return prev
      const { [questionId]: _, ...rest } = prev
      return rest
    })
    setResponses((prev) => {
      const existing = (prev[questionId] ?? '').toString().trim()
      const merged = existing ? `${existing}\n\n${text}` : text
      return { ...prev, [questionId]: merged }
    })
    setErrors((prev) => (prev[questionId] ? { ...prev, [questionId]: null } : prev))
  }, [])

  const submitImageForQuestion = useCallback(
    async (questionId, base64, mimeType = 'image/jpeg') => {
      const q = questions.find((x) => x.id === questionId)
      if (!q) throw new Error('Question not found.')
      const existingCount = photoByQuestionRef.current[questionId]?.images?.length ?? 0
      if (existingCount >= MAX_PHOTOS_PER_QUESTION) {
        throw new Error(
          `You can add at most ${MAX_PHOTOS_PER_QUESTION} photos for this question. Remove one to add another.`,
        )
      }
      setCameraBusy(true)
      setCameraError(null)
      try {
        const headers = { 'Content-Type': 'application/json' }
        if (workflowIdRef.current) headers['X-RxAI-Workflow-Id'] = workflowIdRef.current
        const res = await fetch(`${API_BASE}/analyze-image`, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            image_base64: base64,
            question: q.question,
            question_id: q.id,
            mime_type: mimeType,
          }),
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok) {
          let msg = `Image analysis failed (${res.status})`
          const d = data?.detail
          if (typeof d === 'string') msg = d
          else if (Array.isArray(d) && d.length && d[0]?.msg) msg = String(d[0].msg)
          throw new Error(msg)
        }
        const description = (data.description || '').trim()
        if (!description) throw new Error('No description returned for this image.')
        const rawB64 = base64.includes(',') ? base64.slice(base64.indexOf(',') + 1) : base64
        const preview = `data:${mimeType || 'image/jpeg'};base64,${rawB64}`
        setPhotoByQuestion((prev) => ({
          ...prev,
          [q.id]: {
            images: [...(prev[q.id]?.images || []), { preview, description }],
          },
        }))
        setSkippedQuestions((prev) => {
          if (!prev[q.id]) return prev
          const { [q.id]: _, ...rest } = prev
          return rest
        })
        setErrors((prev) => (prev[q.id] ? { ...prev, [q.id]: null } : prev))
      } finally {
        setCameraBusy(false)
      }
    },
    [questions],
  )

  const handleCameraBlob = useCallback(
    async (base64) => {
      if (!cameraQuestionId) return
      try {
        await submitImageForQuestion(cameraQuestionId, base64, 'image/jpeg')
        setCameraQuestionId(null)
      } catch (err) {
        setCameraError(err.message || 'Image analysis failed')
      }
    },
    [cameraQuestionId, submitImageForQuestion],
  )

  const triggerPhotoUpload = useCallback((questionId) => {
    setCameraError(null)
    uploadTargetQuestionIdRef.current = questionId
    photoFileInputRef.current?.click()
  }, [])

  const handlePhotoFileChange = useCallback(
    (e) => {
      const file = e.target.files?.[0]
      const qid = uploadTargetQuestionIdRef.current
      uploadTargetQuestionIdRef.current = null
      e.target.value = ''
      if (!file || !qid) return
      if (!file.type.startsWith('image/')) {
        setCameraError('Please choose an image file (JPEG, PNG, WebP, or similar).')
        return
      }
      const reader = new FileReader()
      reader.onload = () => {
        const dataUrl = String(reader.result || '')
        const comma = dataUrl.indexOf(',')
        const base64 = comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl
        const mime = file.type && file.type.startsWith('image/') ? file.type : 'image/jpeg'
        ;(async () => {
          try {
            await submitImageForQuestion(qid, base64, mime)
          } catch (err) {
            setCameraError(err.message || 'Image analysis failed')
          }
        })()
      }
      reader.onerror = () => setCameraError('Could not read the selected file.')
      reader.readAsDataURL(file)
    },
    [submitImageForQuestion],
  )

  const handleCheckboxChange = (questionId, option, checked) => {
    setSkippedQuestions((prev) => {
      if (!prev[questionId]) return prev
      const { [questionId]: _, ...rest } = prev
      return rest
    })
    const currentValues = responses[questionId] || []
    const newValues = checked
      ? [...currentValues, option]
      : currentValues.filter((v) => v !== option)
    setResponses((prev) => ({ ...prev, [questionId]: newValues }))
    if (errors[questionId]) {
      setErrors((prev) => ({ ...prev, [questionId]: null }))
    }
  }

  const skipQuestionForId = useCallback(
    (questionId) => {
      const q = questions.find((x) => x.id === questionId)
      if (!q || q.required) return
      setSkippedQuestions((prev) => ({ ...prev, [questionId]: true }))
      setResponses((prev) => {
        const next = { ...prev }
        delete next[questionId]
        return next
      })
      setPhotoByQuestion((prev) => {
        if (!prev[questionId]) return prev
        const { [questionId]: _, ...rest } = prev
        return rest
      })
      setErrors((prev) => {
        if (!prev[questionId]) return prev
        const next = { ...prev }
        delete next[questionId]
        return next
      })
    },
    [questions],
  )

  // ── Validation + submit ─────────────────────────────────────────────────────

  const effectiveSkippedMap = (alsoSkipQuestionId) =>
    alsoSkipQuestionId ? { ...skippedQuestions, [alsoSkipQuestionId]: true } : skippedQuestions

  const validateForm = (alsoSkipQuestionId) => {
    const skipMap = effectiveSkippedMap(alsoSkipQuestionId)
    const newErrors = {}
    questions.forEach((q) => {
      if (skipMap[q.id]) return
      if (q.required) {
        const response = responses[q.id]
        if (!response || (Array.isArray(response) && response.length === 0) || response.trim?.() === '') {
          newErrors[q.id] = 'This question is required'
        }
      }
      if (q.requires_image && !(photoByQuestion[q.id]?.images?.length > 0)) {
        newErrors[q.id] = newErrors[q.id]
          ? `${newErrors[q.id]} Add a photo when prompted.`
          : 'Please add a photo for this question.'
      }
    })
    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e, alsoSkipQuestionId) => {
    e?.preventDefault()
    if (!validateForm(alsoSkipQuestionId)) {
      alert('Please answer all required questions before submitting.')
      return
    }
    const skipMap = effectiveSkippedMap(alsoSkipQuestionId)
    const formattedResponses = {}
    const responsesForSubmit = { ...responses }
    if (alsoSkipQuestionId) {
      delete responsesForSubmit[alsoSkipQuestionId]
    }
    questions.forEach((q) => {
      if (skipMap[q.id]) {
        formattedResponses[q.question] = '[Skipped by patient]'
        responsesForSubmit[q.id] = '[Skipped by patient]'
        return
      }
      const answer = responses[q.id]
      const shots = photoByQuestion[q.id]?.images || []
      let main =
        answer !== undefined && answer !== null && answer !== ''
          ? Array.isArray(answer)
            ? answer.join(', ')
            : answer.toString()
          : ''
      if (shots.length > 0) {
        const photoText = shots
          .map((s, i) => (shots.length > 1 ? `Image ${i + 1}: ${s.description}` : s.description))
          .join('\n\n')
        main = main
          ? `${main}\n\n[Photo assessment]\n${photoText}`
          : `[Photo assessment]\n${photoText}`
      }
      if (main) {
        formattedResponses[q.question] = main
      }
    })
    if (alsoSkipQuestionId) {
      setSkippedQuestions((prev) => ({ ...prev, [alsoSkipQuestionId]: true }))
      setPhotoByQuestion((prev) => {
        if (!prev[alsoSkipQuestionId]) return prev
        const { [alsoSkipQuestionId]: _, ...rest } = prev
        return rest
      })
    }
    onSubmit(questionnaire.id, responsesForSubmit, formattedResponses)
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

    // Recording started → countdown from rolling deadline (supports “Continue recording”)
    if (newStatus === 'listening') {
      silenceDeadlineRef.current = Date.now() + SILENCE_TIMEOUT_MS
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current)
      const tick = () => {
        const left = Math.ceil((silenceDeadlineRef.current - Date.now()) / 1000)
        if (left <= 0) {
          clearInterval(countdownTimerRef.current)
          countdownTimerRef.current = null
          setSilenceCountdown(null)
        } else {
          setSilenceCountdown(left)
        }
      }
      tick()
      countdownTimerRef.current = setInterval(tick, 250)
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

    if (!(q.type === 'text' || q.type === 'multiline' || q.type === 'scale')) return

    setLastTranscript(transcript || '')
    setLastTranscriptConfidence(confidence ?? null)

    if (meta?.needs_rerecord) {
      setVoiceError(meta.message || 'Low transcription confidence. Please re-record your answer.')
    }

    if (q.type === 'text' || q.type === 'multiline') {
      setSkippedQuestions((prev) => {
        if (!prev[q.id]) return prev
        const { [q.id]: _, ...rest } = prev
        return rest
      })
      setResponses((prev) => ({ ...prev, [q.id]: transcript }))
    } else if (q.type === 'scale') {
      const { min: smin, max: smax } = getScaleBounds(q)
      const spoken = parseSpokenScaleValue(transcript, smin, smax)
      if (spoken !== null) {
        setSkippedQuestions((prev) => {
          if (!prev[q.id]) return prev
          const { [q.id]: _, ...rest } = prev
          return rest
        })
        setResponses((prev) => ({ ...prev, [q.id]: spoken }))
      }
    }
    setErrors((prev) => ({ ...prev, [q.id]: null }))
  }, [currentStep, totalSteps, questions])

  // ── Voice mode: errors ───────────────────────────────────────────────────────

  const handleVoiceError = useCallback((err) => {
    setVoiceError(err.message)
  }, [])

  // Dismiss error and let the patient retry manually
  const dismissError = () => setVoiceError(null)

  const handleContinueRecording = useCallback(() => {
    voiceControllerRef.current?.resetSilenceTimer()
    if (voiceStatus === 'listening') {
      silenceDeadlineRef.current = Date.now() + SILENCE_TIMEOUT_MS
    }
  }, [voiceStatus])

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

  const handleVoiceSkip = () => {
    const q = questions[currentStep]
    if (!q || q.required) return
    if (currentStep >= totalSteps - 1) {
      handleSubmit(undefined, q.id)
    } else {
      skipQuestionForId(q.id)
      goToStep(currentStep + 1)
    }
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

  const hiddenPhotoFileInput = (
    <input
      ref={photoFileInputRef}
      type="file"
      accept="image/*"
      className="question-photo-file-input"
      aria-label="Upload image from device"
      onChange={handlePhotoFileChange}
    />
  )

  const renderPhotoSection = (question) => {
    if (!question.requires_image) return null
    const shots = photoByQuestion[question.id]?.images || []
    const hasPhoto = shots.length > 0
    const atPhotoLimit = shots.length >= MAX_PHOTOS_PER_QUESTION
    return (
      <div className="question-photo-block">
        {question.image_prompt && <p className="question-photo-prompt">{question.image_prompt}</p>}

        <div className="question-photo-actions">
          <button
            type="button"
            className="question-photo-btn question-photo-btn--camera"
            onClick={() => {
              setCameraError(null)
              setCameraQuestionId(question.id)
            }}
            disabled={cameraBusy || atPhotoLimit}
            title={atPhotoLimit ? 'Remove a photo to add another' : undefined}
          >
            {hasPhoto ? 'Add with camera' : 'Take photo'}
          </button>
          <button
            type="button"
            className="question-photo-btn question-photo-btn--upload"
            onClick={() => triggerPhotoUpload(question.id)}
            disabled={cameraBusy || atPhotoLimit}
            title={atPhotoLimit ? 'Remove a photo to add another' : undefined}
          >
            {hasPhoto ? 'Add from device' : 'Upload from device'}
          </button>
        </div>

        {hasPhoto && (
          <ul className="question-photo-gallery" aria-label="Uploaded clinical photos and summaries">
            {shots.map((shot, idx) => (
              <li key={`${question.id}-photo-${idx}`} className="question-photo-gallery__item">
                <div className="question-photo-gallery__thumb">
                  <img
                    src={shot.preview}
                    alt={`Clinical photo ${idx + 1} for this question`}
                    loading="lazy"
                  />
                  <button
                    type="button"
                    className="question-photo-remove"
                    onClick={() => removePhotoShot(question.id, idx)}
                    aria-label={`Remove photo ${idx + 1}`}
                    title="Remove this photo"
                  >
                    ×
                  </button>
                </div>
                <div className="question-photo-gallery__summary">
                  <span className="question-photo-gallery__label">Clinical summary</span>
                  <p className="question-photo-gallery__text">{shot.description}</p>
                  {(question.type === 'text' || question.type === 'multiline') && (
                    <button
                      type="button"
                      className="question-photo-insert-btn"
                      onClick={() => insertPhotoSummaryIntoAnswer(question.id, shot.description)}
                      title="Append this text to your written answer. You can edit the field after."
                    >
                      Add to answer above
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        {hasPhoto && !atPhotoLimit && (
          <p className="question-photo-hint">
            Add another angle or a closer view if helpful (up to {MAX_PHOTOS_PER_QUESTION} photos).
          </p>
        )}
        {atPhotoLimit && (
          <p className="question-photo-hint question-photo-hint--limit">
            Maximum {MAX_PHOTOS_PER_QUESTION} photos reached. Remove one above to add a different image.
          </p>
        )}
      </div>
    )
  }

  const cameraOverlay = cameraQuestionId ? (
    <>
      {cameraError && (
        <div className="camera-fetch-error" role="alert">
          {cameraError}
        </div>
      )}
      <CameraCapture
        onCapture={handleCameraBlob}
        onClose={() => {
          setCameraQuestionId(null)
          setCameraError(null)
        }}
        prompt={questions.find((q) => q.id === cameraQuestionId)?.image_prompt}
      />
    </>
  ) : null

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

      case 'scale': {
        const { min: smin, max: smax } = getScaleBounds(question)
        const raw = responses[question.id]
        let numVal = raw !== undefined && raw !== '' ? Number(raw) : smin
        if (!Number.isFinite(numVal)) numVal = smin
        numVal = Math.min(smax, Math.max(smin, numVal))
        const valueStr = String(numVal)
        return (
          <>
            <div className="scale-container">
              <span className="scale-label">{smin}</span>
              <input
                type="range"
                min={smin}
                max={smax}
                step={1}
                value={valueStr}
                onChange={(e) => handleInputChange(question.id, e.target.value)}
                className="scale-input"
                aria-label={`${question.question} — value ${valueStr}`}
              />
              <span className="scale-label">{smax}</span>
            </div>
            <div className="scale-value">
              Current value: <strong>{valueStr}</strong>
            </div>
            {hasError && <span className="error-message" role="alert">{hasError}</span>}
          </>
        )
      }

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
    const answeredCount = questions.filter((q) => {
      if (skippedQuestions[q.id]) return true
      const value = responses[q.id]
      return value && (Array.isArray(value) ? value.length > 0 : String(value).trim() !== '')
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
              const isSkipped = !!skippedQuestions[question.id]
              return (
                <div
                  key={question.id}
                  className={`question-block ${hasError ? 'has-error' : ''} ${isSkipped ? 'question-block--skipped' : ''}`}
                >
                  <div className="question-label-row">
                    <label className="question-label">
                      {index + 1}. {question.question}
                      {question.required && <span className="required">*</span>}
                    </label>
                    {!question.required &&
                      (isSkipped ? (
                        <span className="question-skipped-hint" role="status">
                          Skipped — add an answer to include
                        </span>
                      ) : (
                        <button
                          type="button"
                          className="question-skip-link"
                          onClick={() => skipQuestionForId(question.id)}
                        >
                          Skip
                        </button>
                      ))}
                  </div>
                  {renderQuestionInput(question)}
                  {renderPhotoSection(question)}
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
        {hiddenPhotoFileInput}
        {cameraOverlay}
      </div>
    )
  }

  // ── Voice mode — step-by-step wizard ─────────────────────────────────────────

  const currentQuestion = questions[currentStep]
  const isLastStep = currentStep === totalSteps - 1
  const currentAnswer = currentQuestion ? responses[currentQuestion.id] : undefined
  const currentStepSkipped = currentQuestion && !!skippedQuestions[currentQuestion.id]
  const textOrChoiceOk =
    currentAnswer !== undefined &&
    currentAnswer !== null &&
    (Array.isArray(currentAnswer) ? currentAnswer.length > 0 : currentAnswer.toString().trim() !== '')
  const photoOk =
    !currentQuestion?.requires_image || (photoByQuestion[currentQuestion.id]?.images?.length ?? 0) > 0
  const hasCurrentAnswer = currentStepSkipped || (textOrChoiceOk && photoOk)

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
        workflowId={workflowIdRef.current}
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
            {!currentQuestion.required && skippedQuestions[currentQuestion.id] && (
              <span className="voice-skipped-badge" title="This question was skipped. Answer or add a photo to include it.">
                Skipped
              </span>
            )}
          </div>

          <p className="voice-question-text">{currentQuestion.question}</p>

          <div className="voice-step-body">
            {/* Answer input (editable transcript for text/multiline; standard controls for others) */}
            <div className="voice-answer-area">
              {renderQuestionInput(currentQuestion)}
            </div>

            {renderPhotoSection(currentQuestion)}

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

              {voiceStatus === 'listening' && (
                <button
                  type="button"
                  className="voice-continue-recording-btn"
                  onClick={handleContinueRecording}
                >
                  Continue recording (+{Math.round(SILENCE_TIMEOUT_MS / 1000)}s)
                </button>
              )}

              <button
                type="button"
                className="voice-repeat-btn"
                onClick={() => {
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
            {(currentQuestion.type === 'text' ||
              currentQuestion.type === 'multiline' ||
              currentQuestion.type === 'scale') && (
              <p className="voice-transcript-hint">
                {currentQuestion.type === 'scale'
                  ? 'Say a number in range for the slider, or drag the control — you can edit before moving on.'
                  : 'The mic fills the field above — you can edit it before moving on.'}
              </p>
            )}
          </div>
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

        {currentQuestion && !currentQuestion.required && (
          <button
            type="button"
            className="voice-skip-btn"
            onClick={handleVoiceSkip}
            disabled={voiceStatus === 'speaking' || voiceStatus === 'listening'}
          >
            Skip
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
      {hiddenPhotoFileInput}
      {cameraOverlay}
    </div>
  )
}

export default QuestionnaireForm
