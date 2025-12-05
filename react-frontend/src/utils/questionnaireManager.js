// Questionnaire Manager - Handles questionnaire state across provider and patient views
// Uses localStorage for demo purposes - replace with WebSocket/API in production

export const QuestionnaireManager = {
  // Generate a unique questionnaire ID
  generateQuestionnaireId: (patientId, visitId) => {
    return `${patientId}_${visitId}_${Date.now()}`
  },

  // Release questionnaire to patient
  releaseQuestionnaire: (patientId, visitId, questionnaireData) => {
    const questionnaireId = QuestionnaireManager.generateQuestionnaireId(patientId, visitId)
    
    const questionnaire = {
      id: questionnaireId,
      patientId,
      visitId,
      questions: questionnaireData.questions || [],
      status: 'pending', // pending, in_progress, completed
      releasedAt: new Date().toISOString(),
      completedAt: null,
      responses: {}
    }

    // Store in localStorage (simulate real-time system)
    localStorage.setItem(`questionnaire_${questionnaireId}`, JSON.stringify(questionnaire))
    
    // Store reference for patient
    const patientQuestionnaires = QuestionnaireManager.getPatientQuestionnaires(patientId)
    patientQuestionnaires.push(questionnaireId)
    localStorage.setItem(`patient_questionnaires_${patientId}`, JSON.stringify(patientQuestionnaires))

    return questionnaireId
  },

  // Get all questionnaires for a patient
  getPatientQuestionnaires: (patientId) => {
    const stored = localStorage.getItem(`patient_questionnaires_${patientId}`)
    return stored ? JSON.parse(stored) : []
  },

  // Get pending questionnaires for a patient
  getPendingQuestionnaires: (patientId) => {
    const questionnaireIds = QuestionnaireManager.getPatientQuestionnaires(patientId)
    return questionnaireIds
      .map(id => QuestionnaireManager.getQuestionnaire(id))
      .filter(q => q && (q.status === 'pending' || q.status === 'in_progress'))
  },

  // Get a specific questionnaire
  getQuestionnaire: (questionnaireId) => {
    const stored = localStorage.getItem(`questionnaire_${questionnaireId}`)
    return stored ? JSON.parse(stored) : null
  },

  // Update questionnaire status
  updateQuestionnaireStatus: (questionnaireId, status) => {
    const questionnaire = QuestionnaireManager.getQuestionnaire(questionnaireId)
    if (questionnaire) {
      questionnaire.status = status
      if (status === 'completed') {
        questionnaire.completedAt = new Date().toISOString()
      }
      localStorage.setItem(`questionnaire_${questionnaireId}`, JSON.stringify(questionnaire))
    }
  },

  // Submit questionnaire responses
  submitResponses: (questionnaireId, responses, formattedResponses) => {
    const questionnaire = QuestionnaireManager.getQuestionnaire(questionnaireId)
    if (questionnaire) {
      questionnaire.responses = responses
      questionnaire.formattedResponses = formattedResponses // Question text -> answer
      questionnaire.status = 'completed'
      questionnaire.completedAt = new Date().toISOString()
      localStorage.setItem(`questionnaire_${questionnaireId}`, JSON.stringify(questionnaire))
      
      // Method 1: Dispatch event in current tab
      const event = new CustomEvent('questionnaireCompleted', { 
        detail: { 
          questionnaireId, 
          responses,
          formattedResponses 
        } 
      })
      window.dispatchEvent(event)
      
      // Method 2: Use localStorage to communicate across tabs
      // Set a temporary flag that triggers storage event in other tabs
      const crossTabMessage = {
        type: 'questionnaireCompleted',
        questionnaireId,
        formattedResponses,
        timestamp: Date.now()
      }
      localStorage.setItem('questionnaire_cross_tab_event', JSON.stringify(crossTabMessage))
      
      // Remove the flag immediately (this still triggers storage event in other tabs)
      setTimeout(() => {
        localStorage.removeItem('questionnaire_cross_tab_event')
      }, 100)
      
      console.log('✅ Questionnaire submitted! Events dispatched:', {
        questionnaireId,
        responseCount: Object.keys(formattedResponses).length
      })
    }
  },

  // Get responses for a questionnaire
  getResponses: (questionnaireId) => {
    const questionnaire = QuestionnaireManager.getQuestionnaire(questionnaireId)
    return questionnaire ? questionnaire.responses : null
  },

  // Clear all questionnaires (for testing)
  clearAll: () => {
    const keys = Object.keys(localStorage)
    keys.forEach(key => {
      if (key.startsWith('questionnaire_') || key.startsWith('patient_questionnaires_')) {
        localStorage.removeItem(key)
      }
    })
  }
}

// Dynamic Questionnaire Generation using CrewAI Backend
export const DynamicQuestionnaireGenerator = {
  // API endpoint configuration
  API_BASE_URL: 'http://localhost:8000',

  // Call the AI-powered questionnaire generation API
  generateQuestionnaire: async (patientData, visitContext) => {
    console.log('🤖 Calling AI Questionnaire Generation API')
    console.log('Patient Data:', patientData)
    console.log('Visit Context:', visitContext)
    
    try {
      const response = await fetch(`${DynamicQuestionnaireGenerator.API_BASE_URL}/generate-questionnaire`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          patient_id: patientData.patientId,
          visit_id: visitContext.visitId,
          conditions: patientData.conditions || [],
          medications: patientData.medications || [],
          allergies: patientData.allergies || [],
          issues_detected: visitContext.issues || [],
          clinical_provider_note: visitContext.notes || ''
        })
      })

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `API request failed with status ${response.status}`)
      }

      const data = await response.json()
      console.log('✅ Questionnaire generated successfully:', data)
      
      // Ensure questions have proper structure
      const questions = data.questions || []
      
      return {
        questions: questions.map((q, index) => ({
          id: q.id || `q${index + 1}`,
          type: q.type || 'text',
          question: q.question || '',
          required: q.required !== false, // Default to true
          source: q.source || '',
          rationale: q.rationale || '',
          options: q.options || [],
          min: q.min,
          max: q.max
        }))
      }
    } catch (error) {
      console.error('❌ Error calling questionnaire generation API:', error)
      
      // Check if API server is running
      if (error.message.includes('Failed to fetch') || error.message.includes('NetworkError')) {
        alert('⚠️ Cannot connect to AI server. Make sure the API is running on http://localhost:8000\n\nRun: python api.py')
        throw new Error('API server is not running. Start the server with: python api.py')
      }
      
      throw error
    }
  },

  // Health check to verify API is available
  checkAPIHealth: async () => {
    try {
      const response = await fetch(`${DynamicQuestionnaireGenerator.API_BASE_URL}/patients`)
      return response.ok
    } catch {
      return false
    }
  }
}

