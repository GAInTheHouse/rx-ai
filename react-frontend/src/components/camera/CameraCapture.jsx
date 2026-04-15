import { useCallback, useEffect, useRef, useState } from 'react'
import PropTypes from 'prop-types'
import './CameraCapture.css'

function CameraCapture({ onCapture, onClose, prompt }) {
  const [permission, setPermission] = useState('pending')
  const [hasSnapshot, setHasSnapshot] = useState(false)
  const [error, setError] = useState(null)

  const videoRef = useRef(null)
  const canvasRef = useRef(null)
  const streamRef = useRef(null)

  const stopAllTracks = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
  }, [])

  useEffect(() => {
    let cancelled = false

    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: 'environment' } })
      .then((stream) => {
        if (cancelled) {
          stream.getTracks().forEach((t) => t.stop())
          return
        }
        streamRef.current = stream
        if (videoRef.current) {
          videoRef.current.srcObject = stream
          videoRef.current.play()
        }
        setPermission('granted')
      })
      .catch((err) => {
        if (!cancelled) {
          setPermission('denied')
          setError(
            err.name === 'NotAllowedError'
              ? 'Camera access was denied.'
              : err.name === 'NotFoundError'
              ? 'No camera device was found.'
              : `Camera error: ${err.message}`,
          )
        }
      })

    return () => {
      cancelled = true
      stopAllTracks()
    }
  }, [stopAllTracks])

  const handleSnapshot = () => {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || video.readyState < 2) return

    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height)
    setHasSnapshot(true)
  }

  const handleRetake = () => {
    const canvas = canvasRef.current
    canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height)
    setHasSnapshot(false)
  }

  const handleConfirm = () => {
    if (!hasSnapshot) return
    const base64 = canvasRef.current.toDataURL('image/jpeg', 0.85).split(',')[1]
    stopAllTracks()
    onCapture(base64)
  }

  const handleClose = () => {
    stopAllTracks()
    onClose()
  }

  return (
    <div
      className="camera-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Camera capture"
    >
      <div className="camera-modal">
        <div className="camera-modal-header">
          <div className="camera-modal-header-text">
            <h2 className="camera-modal-title">Take a Photo</h2>
            {prompt && <p className="camera-modal-prompt">{prompt}</p>}
          </div>
          <button
            className="camera-close-btn"
            onClick={handleClose}
            aria-label="Close camera"
            type="button"
          >
            ✕
          </button>
        </div>

        {permission === 'denied' && (
          <div className="camera-error">
            <p>{error}</p>
            <p className="camera-error-hint">
              Please enable camera permissions in your browser settings and reload.
            </p>
          </div>
        )}

        <video
          ref={videoRef}
          className={`camera-video${hasSnapshot ? ' camera-video--hidden' : ''}`}
          autoPlay
          playsInline
          muted
        />

        <canvas
          ref={canvasRef}
          className={`camera-canvas${hasSnapshot ? '' : ' camera-canvas--hidden'}`}
        />

        <div className="camera-actions">
          {!hasSnapshot ? (
            <button
              className="camera-btn camera-btn--capture"
              onClick={handleSnapshot}
              disabled={permission !== 'granted'}
              type="button"
              aria-label="Take photo"
            >
              Take Photo
            </button>
          ) : (
            <>
              <button
                className="camera-btn camera-btn--retake"
                onClick={handleRetake}
                type="button"
              >
                Retake
              </button>
              <button
                className="camera-btn camera-btn--confirm"
                onClick={handleConfirm}
                type="button"
              >
                Use Photo
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

CameraCapture.propTypes = {
  onCapture: PropTypes.func.isRequired,
  onClose: PropTypes.func.isRequired,
  prompt: PropTypes.string,
}

CameraCapture.defaultProps = {
  prompt: null,
}

export default CameraCapture
