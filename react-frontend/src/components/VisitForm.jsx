import { useState, useEffect } from 'react'
import { QuestionnaireManager, DynamicQuestionnaireGenerator } from '../utils/questionnaireManager'
import './VisitForm.css'

function VisitForm({ patientId, onSave, onCancel, visitNumber }) {
  const [formData, setFormData] = useState({
    visit_id: `${patientId}_V${visitNumber}`,
    conditions: [],
    medications: [],
    allergies: [],
    issues_detected: [],
    clinical_provider_note: '',
    questionnaire_responses: null
  })

  const [questionnaireStatus, setQuestionnaireStatus] = useState({
    released: false,
    questionnaireId: null,
    isGenerating: false,
    completed: false
  })

  // Temporary input values for adding items to lists
  const [conditionInput, setConditionInput] = useState('')
  const [medicationInput, setMedicationInput] = useState('')
  const [allergyInput, setAllergyInput] = useState('')
  const [issueInput, setIssueInput] = useState('')

  // Listen for questionnaire completion
  useEffect(() => {
    const handleQuestionnaireCompleted = (event) => {
      console.log('📩 Received questionnaire completion event (CustomEvent):', event.detail)
      
      const { questionnaireId, formattedResponses } = event.detail
      
      if (questionnaireId === questionnaireStatus.questionnaireId) {
        console.log('✅ Matching questionnaire! Updating form with responses:', formattedResponses)
        
        // Auto-populate responses in form (formatted as question -> answer)
        setFormData(prev => ({
          ...prev,
          questionnaire_responses: formattedResponses
        }))
        
        setQuestionnaireStatus(prev => ({
          ...prev,
          completed: true
        }))

        alert('✅ Patient has completed the questionnaire! Responses have been added to this visit.')
      } else {
        console.log('❌ Questionnaire ID mismatch:', {
          expected: questionnaireStatus.questionnaireId,
          received: questionnaireId
        })
      }
    }

    // Listen for cross-tab communication via localStorage
    const handleStorageEvent = (event) => {
      if (event.key === 'questionnaire_cross_tab_event' && event.newValue) {
        console.log('📩 Received questionnaire completion event (Storage):', event.newValue)
        
        try {
          const data = JSON.parse(event.newValue)
          
          if (data.type === 'questionnaireCompleted' && 
              data.questionnaireId === questionnaireStatus.questionnaireId) {
            console.log('✅ Matching questionnaire! Updating form with responses:', data.formattedResponses)
            
            // Auto-populate responses in form
            setFormData(prev => ({
              ...prev,
              questionnaire_responses: data.formattedResponses
            }))
            
            setQuestionnaireStatus(prev => ({
              ...prev,
              completed: true
            }))

            alert('✅ Patient has completed the questionnaire! Responses have been added to this visit.')
          } else {
            console.log('❌ Questionnaire ID mismatch:', {
              expected: questionnaireStatus.questionnaireId,
              received: data.questionnaireId
            })
          }
        } catch (error) {
          console.error('Error parsing storage event:', error)
        }
      }
    }

    // Only add listeners if questionnaire is released
    if (questionnaireStatus.released && questionnaireStatus.questionnaireId) {
      console.log('👂 Listening for questionnaire completion:', questionnaireStatus.questionnaireId)
      console.log('   - CustomEvent listener: active')
      console.log('   - Storage event listener: active (for cross-tab)')
      
      // Listen for same-tab events
      window.addEventListener('questionnaireCompleted', handleQuestionnaireCompleted)
      
      // Listen for cross-tab events via localStorage
      window.addEventListener('storage', handleStorageEvent)
      
      return () => {
        console.log('🔇 Removing questionnaire listeners')
        window.removeEventListener('questionnaireCompleted', handleQuestionnaireCompleted)
        window.removeEventListener('storage', handleStorageEvent)
      }
    }
  }, [questionnaireStatus.questionnaireId, questionnaireStatus.released])

  const handleReleaseQuestionnaire = async () => {
    setQuestionnaireStatus(prev => ({ ...prev, isGenerating: true }))

    try {
      // PLACEHOLDER: Call dynamic questionnaire generation workflow
      const patientData = {
        patientId,
        conditions: formData.conditions,
        medications: formData.medications,
        allergies: formData.allergies
      }

      const visitContext = {
        visitId: formData.visit_id,
        issues: formData.issues_detected,
        notes: formData.clinical_provider_note
      }

      // Generate questionnaire using AI/ML model (placeholder)
      const generatedQuestionnaire = await DynamicQuestionnaireGenerator.generateQuestionnaire(
        patientData,
        visitContext
      )

      // Release questionnaire to patient
      const questionnaireId = QuestionnaireManager.releaseQuestionnaire(
        patientId,
        formData.visit_id,
        generatedQuestionnaire
      )

      setQuestionnaireStatus({
        released: true,
        questionnaireId,
        isGenerating: false,
        completed: false
      })

      alert('✅ Questionnaire has been released to the patient!')
    } catch (error) {
      console.error('Error releasing questionnaire:', error)
      alert('❌ Failed to release questionnaire. Please try again.')
      setQuestionnaireStatus(prev => ({ ...prev, isGenerating: false }))
    }
  }

  const addCondition = () => {
    if (conditionInput.trim()) {
      setFormData({
        ...formData,
        conditions: [...formData.conditions, conditionInput.trim()]
      })
      setConditionInput('')
    }
  }

  const removeCondition = (index) => {
    setFormData({
      ...formData,
      conditions: formData.conditions.filter((_, i) => i !== index)
    })
  }

  const addMedication = () => {
    if (medicationInput.trim()) {
      setFormData({
        ...formData,
        medications: [...formData.medications, medicationInput.trim()]
      })
      setMedicationInput('')
    }
  }

  const removeMedication = (index) => {
    setFormData({
      ...formData,
      medications: formData.medications.filter((_, i) => i !== index)
    })
  }

  const addAllergy = () => {
    if (allergyInput.trim()) {
      setFormData({
        ...formData,
        allergies: [...formData.allergies, allergyInput.trim()]
      })
      setAllergyInput('')
    }
  }

  const removeAllergy = (index) => {
    setFormData({
      ...formData,
      allergies: formData.allergies.filter((_, i) => i !== index)
    })
  }

  const addIssue = () => {
    if (issueInput.trim()) {
      setFormData({
        ...formData,
        issues_detected: [...formData.issues_detected, issueInput.trim()]
      })
      setIssueInput('')
    }
  }

  const removeIssue = (index) => {
    setFormData({
      ...formData,
      issues_detected: formData.issues_detected.filter((_, i) => i !== index)
    })
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    onSave(formData)
  }

  const handleKeyPress = (e, addFunction) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      addFunction()
    }
  }

  return (
    <div className="visit-form-overlay">
      <div className="visit-form-container">
        <div className="visit-form-header">
          <h2>Create New Visit</h2>
          <p className="visit-id-display">Visit ID: {formData.visit_id}</p>
        </div>

        <form onSubmit={handleSubmit} className="visit-form">
          {/* Conditions Section */}
          <div className="form-section">
            <label className="section-label">
              <span className="icon">🏥</span>
              Conditions
            </label>
            <div className="input-with-button">
              <input
                type="text"
                value={conditionInput}
                onChange={(e) => setConditionInput(e.target.value)}
                onKeyPress={(e) => handleKeyPress(e, addCondition)}
                placeholder="Enter a condition and press Add or Enter"
                className="form-input"
              />
              <button type="button" onClick={addCondition} className="add-button">
                + Add
              </button>
            </div>
            <div className="items-list">
              {formData.conditions.map((condition, index) => (
                <div key={index} className="item-tag condition-item">
                  <span>{condition}</span>
                  <button
                    type="button"
                    onClick={() => removeCondition(index)}
                    className="remove-button"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Medications Section */}
          <div className="form-section">
            <label className="section-label">
              <span className="icon">💊</span>
              Medications
            </label>
            <div className="input-with-button">
              <input
                type="text"
                value={medicationInput}
                onChange={(e) => setMedicationInput(e.target.value)}
                onKeyPress={(e) => handleKeyPress(e, addMedication)}
                placeholder="Enter medication (e.g., Metformin 1000mg BID)"
                className="form-input"
              />
              <button type="button" onClick={addMedication} className="add-button">
                + Add
              </button>
            </div>
            <div className="items-list">
              {formData.medications.map((med, index) => (
                <div key={index} className="item-tag medication-item">
                  <span>{med}</span>
                  <button
                    type="button"
                    onClick={() => removeMedication(index)}
                    className="remove-button"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Allergies Section */}
          <div className="form-section">
            <label className="section-label">
              <span className="icon">⚠️</span>
              Allergies
            </label>
            <div className="input-with-button">
              <input
                type="text"
                value={allergyInput}
                onChange={(e) => setAllergyInput(e.target.value)}
                onKeyPress={(e) => handleKeyPress(e, addAllergy)}
                placeholder="Enter an allergy"
                className="form-input"
              />
              <button type="button" onClick={addAllergy} className="add-button">
                + Add
              </button>
            </div>
            <div className="items-list">
              {formData.allergies.map((allergy, index) => (
                <div key={index} className="item-tag allergy-item">
                  <span>{allergy}</span>
                  <button
                    type="button"
                    onClick={() => removeAllergy(index)}
                    className="remove-button"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Issues Detected Section */}
          <div className="form-section">
            <label className="section-label">
              <span className="icon">🔍</span>
              Issues Detected
            </label>
            <div className="input-with-button">
              <input
                type="text"
                value={issueInput}
                onChange={(e) => setIssueInput(e.target.value)}
                onKeyPress={(e) => handleKeyPress(e, addIssue)}
                placeholder="Enter an issue"
                className="form-input"
              />
              <button type="button" onClick={addIssue} className="add-button">
                + Add
              </button>
            </div>
            <div className="items-list">
              {formData.issues_detected.map((issue, index) => (
                <div key={index} className="item-tag issue-item">
                  <span>{issue}</span>
                  <button
                    type="button"
                    onClick={() => removeIssue(index)}
                    className="remove-button"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          </div>

          {/* Clinical Notes Section */}
          <div className="form-section full-width">
            <label className="section-label">
              <span className="icon">📝</span>
              Clinical Provider Notes
            </label>
            <textarea
              value={formData.clinical_provider_note}
              onChange={(e) => setFormData({ ...formData, clinical_provider_note: e.target.value })}
              placeholder="Enter detailed clinical notes about this visit..."
              className="form-textarea"
              rows={6}
            />
          </div>

          {/* Questionnaire Section */}
          <div className="form-section full-width questionnaire-section">
            <label className="section-label">
              <span className="icon">📋</span>
              Patient Questionnaire
            </label>
            
            {!questionnaireStatus.released ? (
              <div className="questionnaire-release">
                <p className="questionnaire-description">
                  Release a dynamically generated questionnaire to the patient to gather additional information about their symptoms and condition.
                </p>
                <button
                  type="button"
                  onClick={handleReleaseQuestionnaire}
                  disabled={questionnaireStatus.isGenerating}
                  className="release-questionnaire-button"
                >
                  {questionnaireStatus.isGenerating ? (
                    <>⏳ Generating Questionnaire...</>
                  ) : (
                    <>📋 Release Questionnaire to Patient</>
                  )}
                </button>
              </div>
            ) : (
              <div className="questionnaire-status">
                {!questionnaireStatus.completed ? (
                  <div className="status-waiting">
                    <div className="status-indicator pending"></div>
                    <div className="status-text">
                      <strong>Questionnaire Released</strong>
                      <p>Waiting for patient to complete the questionnaire...</p>
                    </div>
                  </div>
                ) : (
                  <div className="status-completed">
                    <div className="status-indicator completed"></div>
                    <div className="status-text">
                      <strong>✅ Questionnaire Completed!</strong>
                      <p>Patient responses have been added to this visit and will be saved.</p>
                    </div>
                    {formData.questionnaire_responses && (
                      <div className="responses-preview">
                        <h4>Response Summary:</h4>
                        <div className="response-count">
                          {Object.keys(formData.questionnaire_responses).length} questions answered
                        </div>
                        <div className="responses-list">
                          {Object.entries(formData.questionnaire_responses).slice(0, 3).map(([question, answer], idx) => (
                            <div key={idx} className="response-preview-item">
                              <strong>{question}</strong>
                              <p>{answer.length > 50 ? answer.substring(0, 50) + '...' : answer}</p>
                            </div>
                          ))}
                          {Object.keys(formData.questionnaire_responses).length > 3 && (
                            <p className="more-responses">
                              + {Object.keys(formData.questionnaire_responses).length - 3} more responses
                            </p>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Form Actions */}
          <div className="form-actions">
            <button type="button" onClick={onCancel} className="cancel-button">
              Cancel
            </button>
            <button type="submit" className="save-button">
              Save Visit
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default VisitForm

