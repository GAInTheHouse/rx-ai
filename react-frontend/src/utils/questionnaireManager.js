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

// PLACEHOLDER: Dynamic Questionnaire Generation Workflow
// This is where the AI-powered questionnaire generation will be integrated
export const DynamicQuestionnaireGenerator = {
  // This will eventually call your AI/ML model to generate contextual questions
  generateQuestionnaire: async (patientData, visitContext) => {
    console.log('🤖 PLACEHOLDER: Dynamic Questionnaire Generation Workflow')
    console.log('Patient Data:', patientData)
    console.log('Visit Context:', visitContext)
    console.log('⚡ This is where the AI model will generate personalized questions')
    
    // TODO: Replace with actual AI model call
    // Example: const response = await fetch('/api/generate-questionnaire', { ... })
    
    // For now, return sample questions
    return {
      questions: [
        {
          id: 'q1',
          type: 'text',
          question: 'How are you feeling today?',
          required: true
        },
        {
          id: 'q2',
          type: 'scale',
          question: 'On a scale of 1-10, how would you rate your pain level?',
          required: true,
          min: 1,
          max: 10
        },
        {
          id: 'q3',
          type: 'multiline',
          question: 'Please describe any symptoms you\'ve been experiencing since your last visit.',
          required: true
        },
        {
          id: 'q4',
          type: 'checkbox',
          question: 'Which of the following have you experienced? (Select all that apply)',
          options: ['Fatigue', 'Headaches', 'Dizziness', 'Nausea', 'Other'],
          required: false
        },
        {
          id: 'q5',
          type: 'radio',
          question: 'Are you taking your medications as prescribed?',
          options: ['Yes, always', 'Most of the time', 'Sometimes', 'Rarely', 'No'],
          required: true
        }
      ]
    }
  }
}

