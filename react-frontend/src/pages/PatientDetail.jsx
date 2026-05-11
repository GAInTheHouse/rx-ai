import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import VisitForm from '../components/VisitForm'
import './PatientDetail.css'

function PatientDetail() {
  const { patientId } = useParams()
  const navigate = useNavigate()
  const [patient, setPatient] = useState(null)
  const [selectedVisitIndex, setSelectedVisitIndex] = useState(0)
  const [loading, setLoading] = useState(true)
  const [showVisitForm, setShowVisitForm] = useState(false)

  useEffect(() => {
    // Load patient data
    fetch('/data/final_merged_patient_data.json')
      .then(response => response.json())
      .then(data => {
        const foundPatient = data.find(p => p.patient_id === patientId)
        if (foundPatient) {
          setPatient(foundPatient)
          setSelectedVisitIndex(foundPatient.visits.length - 1) // Start with most recent visit
        }
        setLoading(false)
      })
      .catch(error => {
        console.error('Error loading patient data:', error)
        setLoading(false)
      })
  }, [patientId])

  const handleSaveNewVisit = (newVisitData) => {
    console.log('💾 Saving new visit with data:', newVisitData)
    
    // Ensure questionnaire_responses is properly structured
    const visitToSave = {
      ...newVisitData,
      questionnaire_responses: newVisitData.questionnaire_responses || null
    }
    
    // Add the new visit to the patient's visits array
    const updatedPatient = {
      ...patient,
      visits: [...patient.visits, visitToSave]
    }
    
    setPatient(updatedPatient)
    setSelectedVisitIndex(updatedPatient.visits.length - 1) // Switch to the new visit
    setShowVisitForm(false)
    
    // Here you would typically also save to a backend API
    console.log('✅ New visit created with questionnaire responses:', {
      visitId: visitToSave.visit_id,
      hasQuestionnaireResponses: !!visitToSave.questionnaire_responses,
      responseCount: visitToSave.questionnaire_responses 
        ? Object.keys(visitToSave.questionnaire_responses).length 
        : 0
    })
    
    alert('Visit saved successfully!' + 
      (visitToSave.questionnaire_responses 
        ? ` (${Object.keys(visitToSave.questionnaire_responses).length} questionnaire responses included)` 
        : ''))
  }

  const handleCancelNewVisit = () => {
    setShowVisitForm(false)
  }

  if (loading) {
    return (
      <div className="patient-detail-loading">
        <h2>Loading patient data...</h2>
      </div>
    )
  }

  if (!patient) {
    return (
      <div className="patient-detail-error">
        <h2>Patient not found</h2>
        <button onClick={() => navigate('/')} className="back-button">
          Back to Patient List
        </button>
      </div>
    )
  }

  const selectedVisit = patient.visits[selectedVisitIndex]

  return (
    <div className="patient-detail-container">
      {/* Header Section */}
      <div className="detail-header">
        <div className="header-actions">
          <button onClick={() => navigate('/')} className="back-button">
            ← Back to Patients
          </button>
          <button onClick={() => setShowVisitForm(true)} className="new-visit-button">
            + Create New Visit
          </button>
        </div>
        <div className="patient-header-info">
          <h1>{patient.patient_id}</h1>
          <div className="patient-demographics">
            <span className="demo-item">Age: {patient.history?.age || 'N/A'}</span>
            <span className="demo-item">Sex: {patient.history?.sex || 'N/A'}</span>
            <span className="demo-item">Height: {patient.history?.height || 'N/A'}</span>
          </div>
        </div>
      </div>

      {/* Visit Selector */}
      <div className="visit-selector-section">
        <h2>Patient Visits ({patient.visits.length})</h2>
        <div className="visit-tabs">
          {patient.visits.map((visit, index) => (
            <button
              key={visit.visit_id}
              className={`visit-tab ${index === selectedVisitIndex ? 'active' : ''}`}
              onClick={() => setSelectedVisitIndex(index)}
            >
              <div className="visit-tab-title">Visit {index + 1}</div>
              <div className="visit-tab-id">{visit.visit_id}</div>
            </button>
          ))}
        </div>
      </div>

      {/* Visit Details */}
      {selectedVisit && (
        <div className="visit-details">
          <div className="visit-header">
            <h2>Visit Details: {selectedVisit.visit_id}</h2>
          </div>

          <div className="details-grid">
            {/* Conditions */}
            <div className="detail-card">
              <h3>
                <span className="icon">🏥</span>
                Current Conditions
              </h3>
              <div className="detail-content">
                {selectedVisit.conditions && selectedVisit.conditions.length > 0 ? (
                  <ul className="detail-list">
                    {selectedVisit.conditions.map((condition, idx) => (
                      <li key={idx} className="condition-item">{condition}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">No conditions recorded</p>
                )}
              </div>
            </div>

            {/* Medications */}
            <div className="detail-card">
              <h3>
                <span className="icon">💊</span>
                Medications
              </h3>
              <div className="detail-content">
                {selectedVisit.medications && selectedVisit.medications.length > 0 ? (
                  <ul className="detail-list">
                    {selectedVisit.medications.map((med, idx) => (
                      <li key={idx} className="medication-item">{med}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">No medications recorded</p>
                )}
              </div>
            </div>

            {/* Allergies */}
            <div className="detail-card">
              <h3>
                <span className="icon">⚠️</span>
                Allergies
              </h3>
              <div className="detail-content">
                {selectedVisit.allergies && selectedVisit.allergies.length > 0 ? (
                  <ul className="detail-list">
                    {selectedVisit.allergies.map((allergy, idx) => (
                      <li key={idx} className="allergy-item">{allergy}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">No known allergies</p>
                )}
              </div>
            </div>

            {/* Issues Detected */}
            <div className="detail-card">
              <h3>
                <span className="icon">🔍</span>
                Issues Detected
              </h3>
              <div className="detail-content">
                {selectedVisit.issues_detected && selectedVisit.issues_detected.length > 0 ? (
                  <ul className="detail-list">
                    {selectedVisit.issues_detected.map((issue, idx) => (
                      <li key={idx} className="issue-item">{issue}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="no-data">No issues detected</p>
                )}
              </div>
            </div>
          </div>

          {/* Clinical Notes - Full Width */}
          {selectedVisit.clinical_provider_note && (
            <div className="detail-card clinical-notes">
              <h3>
                <span className="icon">📝</span>
                Clinical Provider Notes
              </h3>
              <div className="detail-content">
                <p className="clinical-note-text">{selectedVisit.clinical_provider_note}</p>
              </div>
            </div>
          )}

          {/* Questionnaire Responses - Full Width */}
          {selectedVisit.questionnaire_responses && Object.keys(selectedVisit.questionnaire_responses).length > 0 && (
            <div className="detail-card questionnaire-responses">
              <h3>
                <span className="icon">📋</span>
                Patient Questionnaire Responses
              </h3>
              <div className="detail-content">
                <div className="questionnaire-responses-grid">
                  {Object.entries(selectedVisit.questionnaire_responses).map(([question, answer], idx) => (
                    <div key={idx} className="questionnaire-response-item">
                      <div className="question-text">{question}</div>
                      <div className="answer-text">{answer}</div>
                      {selectedVisit.questionnaire_images &&
                        selectedVisit.questionnaire_images[question] &&
                        Array.isArray(selectedVisit.questionnaire_images[question].images) &&
                        selectedVisit.questionnaire_images[question].images.length > 0 && (
                          <div className="questionnaire-image-strip" aria-label="Patient uploaded images">
                            {selectedVisit.questionnaire_images[question].images.map((img, i) => (
                              <img
                                key={i}
                                src={img.preview}
                                alt={`Patient uploaded image ${i + 1}`}
                                className="questionnaire-image-thumb"
                                loading="lazy"
                              />
                            ))}
                          </div>
                        )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Visit Form Modal */}
      {showVisitForm && (
        <VisitForm
          patientId={patient.patient_id}
          visitNumber={patient.visits.length + 1}
          onSave={handleSaveNewVisit}
          onCancel={handleCancelNewVisit}
        />
      )}
    </div>
  )
}

export default PatientDetail

