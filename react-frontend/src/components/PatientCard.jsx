import { useNavigate } from 'react-router-dom'
import './PatientCard.css'

function PatientCard({ patient }) {
  const navigate = useNavigate()
  const { patient_id, history, visits } = patient
  const latestVisit = visits?.[visits.length - 1]
  const visitCount = visits?.length || 0

  const handleClick = () => {
    navigate(`/patient/${patient_id}`)
  }

  return (
    <div className="patient-card" onClick={handleClick}>
      <div className="patient-card-header">
        <h3 className="patient-id">{patient_id}</h3>
        <span className="visit-badge">{visitCount} visit{visitCount !== 1 ? 's' : ''}</span>
      </div>
      
      <div className="patient-info">
        <div className="info-row">
          <span className="info-label">Age:</span>
          <span className="info-value">{history?.age || 'N/A'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Sex:</span>
          <span className="info-value">{history?.sex || 'N/A'}</span>
        </div>
        <div className="info-row">
          <span className="info-label">Height:</span>
          <span className="info-value">{history?.height || 'N/A'}</span>
        </div>
      </div>

      {latestVisit && (
        <div className="latest-conditions">
          <h4>Current Conditions:</h4>
          <div className="condition-tags">
            {latestVisit.conditions?.slice(0, 3).map((condition, index) => (
              <span key={index} className="condition-tag">{condition}</span>
            ))}
            {latestVisit.conditions?.length > 3 && (
              <span className="condition-tag more">+{latestVisit.conditions.length - 3} more</span>
            )}
          </div>
        </div>
      )}

      <div className="card-footer">
        <button className="view-button">View Details</button>
      </div>
    </div>
  )
}

export default PatientCard

