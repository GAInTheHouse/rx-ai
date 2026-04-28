import './VoiceStatusBar.css'

/**
 * Animated status bar that reflects the VoiceController lifecycle.
 *
 * Props:
 *   status — 'idle' | 'speaking' | 'listening'
 *   error  — string | null — displayed below the bar when set
 *   silenceCountdown — number | null — remaining seconds before auto-stop
 */
function VoiceStatusBar({ status = 'idle', error = null, silenceCountdown = null }) {
  const label =
    status === 'speaking' ? 'Speaking…' :
    status === 'listening' ? (silenceCountdown != null ? `Listening… (${silenceCountdown}s)` : 'Listening…') :
    'Voice ready'

  const ariaLabel =
    status === 'speaking' ? 'Speaking question aloud' :
    status === 'listening' ? 'Listening for your answer' :
    'Voice ready'

  return (
    <div
      className={`vsb vsb--${status}`}
      role="status"
      aria-live="polite"
      aria-label={ariaLabel}
    >
      <div className="vsb__inner">
        {status === 'speaking' && <Waveform />}
        {status === 'listening' && <ListeningRing />}
        {status === 'idle' && <IdleDot />}
        <span className="vsb__label">{label}</span>
      </div>
      {error && (
        <p className="vsb__error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

function Waveform() {
  return (
    <div className="vsb-waveform" aria-hidden="true">
      {[1, 2, 3, 4, 5].map((i) => (
        <span key={i} className={`vsb-waveform__bar vsb-waveform__bar--${i}`} />
      ))}
    </div>
  )
}

function ListeningRing() {
  return (
    <div className="vsb-ring" aria-hidden="true">
      <span className="vsb-ring__pulse" />
      <span className="vsb-ring__icon">🎤</span>
    </div>
  )
}

function IdleDot() {
  return <span className="vsb-idle" aria-hidden="true" />
}

export default VoiceStatusBar
