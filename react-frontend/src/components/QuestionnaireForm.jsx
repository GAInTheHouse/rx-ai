import { useState } from 'react'
import './QuestionnaireForm.css'

function QuestionnaireForm({ questionnaire, onSubmit, onCancel }) {
  const [responses, setResponses] = useState({})
  const [errors, setErrors] = useState({})

  const handleInputChange = (questionId, value) => {
    setResponses({
      ...responses,
      [questionId]: value
    })
    // Clear error for this question
    if (errors[questionId]) {
      setErrors({
        ...errors,
        [questionId]: null
      })
    }
  }

  const handleCheckboxChange = (questionId, option, checked) => {
    const currentValues = responses[questionId] || []
    const newValues = checked
      ? [...currentValues, option]
      : currentValues.filter(v => v !== option)
    
    setResponses({
      ...responses,
      [questionId]: newValues
    })
  }

  const validateForm = () => {
    const newErrors = {}
    
    questionnaire.questions.forEach(question => {
      if (question.required) {
        const response = responses[question.id]
        if (!response || (Array.isArray(response) && response.length === 0) || response.trim?.() === '') {
          newErrors[question.id] = 'This question is required'
        }
      }
    })

    setErrors(newErrors)
    return Object.keys(newErrors).length === 0
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    
    if (validateForm()) {
      onSubmit(questionnaire.id, responses)
    } else {
      alert('Please answer all required questions before submitting.')
    }
  }

  const renderQuestion = (question, index) => {
    const hasError = errors[question.id]

    switch (question.type) {
      case 'text':
        return (
          <div key={question.id} className={`question-block ${hasError ? 'has-error' : ''}`}>
            <label className="question-label">
              {index + 1}. {question.question}
              {question.required && <span className="required">*</span>}
            </label>
            <input
              type="text"
              value={responses[question.id] || ''}
              onChange={(e) => handleInputChange(question.id, e.target.value)}
              className="question-input"
              placeholder="Type your answer..."
            />
            {hasError && <span className="error-message">{hasError}</span>}
          </div>
        )

      case 'multiline':
        return (
          <div key={question.id} className={`question-block ${hasError ? 'has-error' : ''}`}>
            <label className="question-label">
              {index + 1}. {question.question}
              {question.required && <span className="required">*</span>}
            </label>
            <textarea
              value={responses[question.id] || ''}
              onChange={(e) => handleInputChange(question.id, e.target.value)}
              className="question-textarea"
              placeholder="Type your answer..."
              rows={4}
            />
            {hasError && <span className="error-message">{hasError}</span>}
          </div>
        )

      case 'scale':
        return (
          <div key={question.id} className={`question-block ${hasError ? 'has-error' : ''}`}>
            <label className="question-label">
              {index + 1}. {question.question}
              {question.required && <span className="required">*</span>}
            </label>
            <div className="scale-container">
              <span className="scale-label">{question.min}</span>
              <input
                type="range"
                min={question.min}
                max={question.max}
                value={responses[question.id] || question.min}
                onChange={(e) => handleInputChange(question.id, e.target.value)}
                className="scale-input"
              />
              <span className="scale-label">{question.max}</span>
            </div>
            <div className="scale-value">
              Current value: <strong>{responses[question.id] || question.min}</strong>
            </div>
            {hasError && <span className="error-message">{hasError}</span>}
          </div>
        )

      case 'radio':
        return (
          <div key={question.id} className={`question-block ${hasError ? 'has-error' : ''}`}>
            <label className="question-label">
              {index + 1}. {question.question}
              {question.required && <span className="required">*</span>}
            </label>
            <div className="options-container">
              {question.options.map(option => (
                <label key={option} className="radio-option">
                  <input
                    type="radio"
                    name={question.id}
                    value={option}
                    checked={responses[question.id] === option}
                    onChange={(e) => handleInputChange(question.id, e.target.value)}
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
            {hasError && <span className="error-message">{hasError}</span>}
          </div>
        )

      case 'checkbox':
        return (
          <div key={question.id} className={`question-block ${hasError ? 'has-error' : ''}`}>
            <label className="question-label">
              {index + 1}. {question.question}
              {question.required && <span className="required">*</span>}
            </label>
            <div className="options-container">
              {question.options.map(option => (
                <label key={option} className="checkbox-option">
                  <input
                    type="checkbox"
                    checked={(responses[question.id] || []).includes(option)}
                    onChange={(e) => handleCheckboxChange(question.id, option, e.target.checked)}
                  />
                  <span>{option}</span>
                </label>
              ))}
            </div>
            {hasError && <span className="error-message">{hasError}</span>}
          </div>
        )

      default:
        return null
    }
  }

  const answeredCount = Object.keys(responses).filter(key => {
    const value = responses[key]
    return value && (Array.isArray(value) ? value.length > 0 : value.trim() !== '')
  }).length

  return (
    <div className="questionnaire-form-container">
      <div className="questionnaire-header">
        <h1>Patient Questionnaire</h1>
        <p className="questionnaire-meta">
          Visit: {questionnaire.visitId} | Released: {new Date(questionnaire.releasedAt).toLocaleDateString()}
        </p>
        <div className="progress-indicator">
          <span className="progress-text">
            Progress: {answeredCount} / {questionnaire.questions.length} questions
          </span>
          <div className="progress-bar">
            <div 
              className="progress-fill" 
              style={{ width: `${(answeredCount / questionnaire.questions.length) * 100}%` }}
            />
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="questionnaire-form">
        <div className="questions-list">
          {questionnaire.questions.map((question, index) => renderQuestion(question, index))}
        </div>

        <div className="form-actions">
          <button type="button" onClick={onCancel} className="cancel-button">
            Cancel
          </button>
          <button type="submit" className="submit-button">
            Submit Questionnaire
          </button>
        </div>
      </form>
    </div>
  )
}

export default QuestionnaireForm

