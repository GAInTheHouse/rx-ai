import { useState, useEffect } from 'react'
import PatientCard from '../components/PatientCard'
import './PatientList.css'

function PatientList() {
  const [patients, setPatients] = useState([])
  const [loading, setLoading] = useState(true)
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    // Load patient data
    fetch('/data/final_merged_patient_data.json')
      .then(response => response.json())
      .then(data => {
        setPatients(data)
        setLoading(false)
      })
      .catch(error => {
        console.error('Error loading patient data:', error)
        setLoading(false)
      })
  }, [])

  const filteredPatients = patients.filter(patient => {
    const searchLower = searchTerm.toLowerCase()
    return (
      patient.patient_id.toLowerCase().includes(searchLower) ||
      (patient.history?.age?.toString().includes(searchLower)) ||
      (patient.history?.sex?.toLowerCase().includes(searchLower))
    )
  })

  if (loading) {
    return (
      <div>
        <h1>Loading patients...</h1>
      </div>
    )
  }

  return (
    <div className="patient-list-container">
      <div className="patient-list-header">
        <h1>Welcome Dr. Shreya,</h1>
        <p className="subtitle">You have {patients.length} patients in your care</p>
      </div>

      <div className="search-bar">
        <input
          type="text"
          placeholder="Search patients by ID, age, or sex..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="search-input"
        />
      </div>

      <div className="patient-grid">
        {filteredPatients.length > 0 ? (
          filteredPatients.map(patient => (
            <PatientCard key={patient.patient_id} patient={patient} />
          ))
        ) : (
          <p className="no-results">No patients found matching your search.</p>
        )}
      </div>
    </div>
  )
}

export default PatientList

