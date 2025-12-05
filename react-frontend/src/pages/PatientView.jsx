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

  useEffect(() => {
    loadPendingQuestionnaires()
    
    // Poll for new questionnaires every 3 seconds (simulate real-time)
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

  const handleSubmitQuestionnaire = (questionnaireId, responses) => {
    QuestionnaireManager.submitResponses(questionnaireId, responses)
    setSelectedQuestionnaire(null)
    loadPendingQuestionnaires()
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
        <h2>Loading...</h2>
      </div>
    )
  }

  if (selectedQuestionnaire) {
    return (
      <QuestionnaireForm
        questionnaire={selectedQuestionnaire}
        onSubmit={handleSubmitQuestionnaire}
        onCancel={handleCancelQuestionnaire}
      />
    )
  }

  return (
    <div className="patient-view-container">
      <div className="patient-view-header">
        <h1>Patient Portal</h1>
        <p className="patient-id">Patient ID: {patientId}</p>
      </div>

      <div className="questionnaires-section">
        <h2>Available Questionnaires</h2>
        
        {pendingQuestionnaires.length === 0 ? (
          <div className="no-questionnaires">
            <div className="empty-state">
              <span className="empty-icon">📋</span>
              <h3>No Questionnaires Available</h3>
              <p>Your doctor hasn't released any questionnaires yet. Please check back later.</p>
            </div>
          </div>
        ) : (
          <div className="questionnaire-cards">
            {pendingQuestionnaires.map(questionnaire => (
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
                  <p className="visit-info">
                    Visit: {questionnaire.visitId}
                  </p>
                </div>
                <div className="card-footer">
                  <button
                    onClick={() => handleStartQuestionnaire(questionnaire)}
                    className="start-button"
                  >
                    Start Questionnaire →
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
          Your healthcare provider may release questionnaires to gather information about your symptoms, 
          medication compliance, and overall health status. Please complete them as soon as possible to 
          help your provider give you the best care.
        </p>
      </div>
    </div>
  )
}

export default PatientView

