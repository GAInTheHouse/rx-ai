import PropTypes from 'prop-types'
import './ImagePreview.css'

function ImagePreview({ base64, onRetake, description, isAnalyzing }) {
  return (
    <div className="image-preview">
      <div className="image-preview-thumbnail-wrapper">
        <img
          src={`data:image/jpeg;base64,${base64}`}
          alt="Captured photo"
          className="image-preview-thumbnail"
        />
        {isAnalyzing && (
          <div className="image-preview-analyzing-overlay" aria-live="polite">
            <span className="image-preview-spinner" aria-hidden="true" />
            <span>Analyzing...</span>
          </div>
        )}
      </div>

      {description && (
        <p className="image-preview-description">{description}</p>
      )}

      <button
        className="image-preview-retake-btn"
        onClick={onRetake}
        type="button"
        aria-label="Retake photo"
      >
        Retake Photo
      </button>
    </div>
  )
}

ImagePreview.propTypes = {
  base64: PropTypes.string.isRequired,
  onRetake: PropTypes.func.isRequired,
  description: PropTypes.string,
  isAnalyzing: PropTypes.bool,
}

ImagePreview.defaultProps = {
  description: null,
  isAnalyzing: false,
}

export default ImagePreview
