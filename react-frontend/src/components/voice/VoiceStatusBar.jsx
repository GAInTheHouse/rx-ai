import PropTypes from 'prop-types'
import './VoiceStatusBar.css'

/**
 * Animated status indicator for the voice pipeline.
 *
 * Props:
 *   status — 'idle' | 'speaking' | 'listening'
 */
function VoiceStatusBar({ status }) {
  if (status === 'idle') return null

  return (
    <div className={`voice-status-bar voice-status-bar--${status}`} aria-live="polite">
      {status === 'speaking' && (
        <>
          <div className="vsb-waveform" aria-hidden="true">
            {[1, 2, 3, 4, 5].map((i) => (
              <span key={i} className={`vsb-bar vsb-bar--${i}`} />
            ))}
          </div>
          <span className="vsb-label">Speaking…</span>
        </>
      )}

      {status === 'listening' && (
        <>
          <span className="vsb-mic-pulse" aria-hidden="true">🎤</span>
          <span className="vsb-label">Listening…</span>
        </>
      )}
    </div>
  )
}

VoiceStatusBar.propTypes = {
  status: PropTypes.oneOf(['idle', 'speaking', 'listening']).isRequired,
}

export default VoiceStatusBar
