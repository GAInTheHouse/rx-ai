import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import PatientList from './pages/PatientList'
import PatientDetail from './pages/PatientDetail'
import './App.css'

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<PatientList />} />
          <Route path="/patient/:patientId" element={<PatientDetail />} />
        </Routes>
      </Layout>
    </Router>
  )
}

export default App

