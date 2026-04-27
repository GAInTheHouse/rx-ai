import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import { QuestionnaireManager } from '../utils/questionnaireManager'
import QuestionnaireForm from '../components/QuestionnaireForm'
import './PatientView.css'

function PatientView() {
  const { patientId } = useParams()
  const [pendingQuestionnaires, setPendingQuestionnaires] = useState([])
  const [selectedQuestionnaire, setSelectedQuestionnaire] = useState(null)
  const [loading, setLoading] = useState(true)
  const [voiceMode, setVoiceMode] = useState(false)

  useEffect(() => {
    loadPendingQuestionnaires()
    const interval = setInterval(loadPendingQuestionnaires, 3000)
    return () => clearInterval(interval)
  }, [patientId])

  const loadPendingQuestionnaires = () => {
    const questionnaires = QuestionnaireManager.getPendingQuestionnaires(patientId)
    setPendingQuestionnaires(questionnaires)
    setLoading(false)
  }

  const handleStartQuestionnaire = (questionnaire) => {
    QuestionnaireManager.updateQuestionnaireStatus(questionnaire.id, 'in_progress')
    setSelectedQuestionnaire(questionnaire)
  }

  const handleSubmitQuestionnaire = (questionnaireId, responses, formattedResponses) => {
    QuestionnaireManager.submitResponses(questionnaireId, responses, formattedResponses)
    setSelectedQuestionnaire(null)
    loadPendingQuestionnaires()
    alert('✅ Questionnaire submitted successfully! Your responses have been sent to your provider.')
  }

  const handleCancelQuestionnaire = () => {
    if (selectedQuestionnaire) {
      QuestionnaireManager.updateQuestionnaireStatus(selectedQuestionnaire.id, 'pending')
    }
    setSelectedQuestionnaire(null)
  }

  if (loading) {
    return (
      <div className="patient-view-container">
        <h2>Loading…</h2>
      </div>
    )
  }

  if (selectedQuestionnaire) {
    return (
      <QuestionnaireForm
        questionnaire={selectedQuestionnaire}
        onSubmit={handleSubmitQuestionnaire}
        onCancel={handleCancelQuestionnaire}
        voiceMode={voiceMode}
      />
    )
  }

  return (
    <div className="patient-view-container">
      <div className="patient-view-header">
        <div className="patient-view-header-top">
          <div>
            <h1>Patient Portal</h1>
            <p className="patient-id">Patient ID: {patientId}</p>
          </div>

          {/* ── Voice + Camera mode toggle ─────────────────────────── */}
          <div className="voice-mode-toggle-wrapper">
            <span className="voice-mode-toggle-label">Input mode</span>
            <div className="voice-mode-toggle-group" role="group" aria-label="Input mode">
              <button
                type="button"
                className={`voice-mode-btn${!voiceMode ? ' voice-mode-btn--active' : ''}`}
                onClick={() => setVoiceMode(false)}
                aria-pressed={!voiceMode}
              >
                ⌨️ Text only
              </button>
              <button
                type="button"
                className={`voice-mode-btn${voiceMode ? ' voice-mode-btn--active' : ''}`}
                onClick={() => setVoiceMode(true)}
                aria-pressed={voiceMode}
              >
                🎤 Voice + Camera
              </button>
            </div>
            {voiceMode && (
              <p className="voice-mode-hint">
                Questions will use voice input and camera where needed.
              </p>
            )}
          </div>
        </div>
      </div>

      <div className="questionnaires-section">
        <h2>Available Questionnaires</h2>

        {pendingQuestionnaires.length === 0 ? (
          <div className="no-questionnaires">
            <div className="empty-state">
              <span className="empty-icon">📋</span>
              <h3>No Questionnaires Available</h3>
              <p>Your doctor hasn&apos;t released any questionnaires yet. Please check back later.</p>
            </div>
          </div>
        ) : (
          <div className="questionnaire-cards">
            {pendingQuestionnaires.map((questionnaire) => (
              <div key={questionnaire.id} className="questionnaire-card">
                <div className="card-header">
                  <h3>New Questionnaire</h3>
                  <span className="status-badge pending">Pending</span>
                </div>
                <div className="card-body">
                  <p className="release-time">
                    Released: {new Date(questionnaire.releasedAt).toLocaleString()}
                  </p>
                  <p className="question-count">
                    {questionnaire.questions.length} questions to answer
                  </p>
                  <p className="visit-info">Visit: {questionnaire.visitId}</p>
                </div>
                <div className="card-footer">
                  <button
                    onClick={() => handleStartQuestionnaire(questionnaire)}
                    className="start-button"
                  >
                    {voiceMode ? '🎤 Start with Voice + Camera →' : 'Start Questionnaire →'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="patient-info-box">
        <h3>ℹ️ Information</h3>
        <p>
          Your healthcare provider may release questionnaires to gather information about your
          symptoms, medication compliance, and overall health status. Please complete them as soon
          as possible to help your provider give you the best care.
        </p>
      </div>
    </div>
  )
}

export default PatientView
