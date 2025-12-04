import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import PatientList from './pages/PatientList'
import PatientDetail from './pages/PatientDetail'
import PatientView from './pages/PatientView'
import './App.css'

function App() {
  return (
    <Router>
      <Routes>
        {/* Provider routes (with layout) */}
        <Route path="/" element={<Layout><PatientList /></Layout>} />
        <Route path="/patient/:patientId" element={<Layout><PatientDetail /></Layout>} />
        
        {/* Patient routes (no layout - separate interface) */}
        <Route path="/patient-portal/:patientId" element={<PatientView />} />
      </Routes>
    </Router>
  )
}

export default App

