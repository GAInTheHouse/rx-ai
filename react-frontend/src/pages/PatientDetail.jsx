import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import './PatientDetail.css'

function PatientDetail() {
  const { patientId } = useParams()
  const navigate = useNavigate()
  const [patient, setPatient] = useState(null)
  const [selectedVisitIndex, setSelectedVisitIndex] = useState(0)
  const [loading, setLoading] = useState(true)

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
        <button onClick={() => navigate('/')} className="back-button">
          ← Back to Patients
        </button>
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
        </div>
      )}
    </div>
  )
}

export default PatientDetail

