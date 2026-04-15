// Module-level session state — only one recording active at a time
let _mediaRecorder = null
let _stream = null
let _chunks = []

/**
 * Returns the best audio MIME type supported by this browser's MediaRecorder.
 * Preference order: webm/opus (Chrome/Firefox) → mp4 (Safari) → ogg/opus → plain webm.
 * Returns '' if MediaRecorder is unavailable (non-secure context, unsupported browser).
 */
export function getSupportedMimeType() {
  if (typeof MediaRecorder === 'undefined') return ''
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/mp4',
    'audio/ogg;codecs=opus',
    'audio/webm',
  ]
  return candidates.find((t) => MediaRecorder.isTypeSupported(t)) ?? ''
}

/**
 * Requests microphone access and starts a MediaRecorder session.
 * Resolves with the MIME type that was selected.
 * Rejects if MediaRecorder is unsupported, getUserMedia is denied, or recorder
 * construction fails. On any post-getUserMedia failure the mic stream is always
 * released before rethrowing.
 */
export async function startRecording() {
  if (typeof MediaRecorder === 'undefined') {
    throw new Error(
      'MediaRecorder is not supported in this browser or context (HTTPS required outside localhost)',
    )
  }

  if (_mediaRecorder && _mediaRecorder.state !== 'inactive') {
    throw new Error('A recording session is already active')
  }

  _stream = await navigator.mediaDevices.getUserMedia({ audio: true })

  const mimeType = getSupportedMimeType()
  const options = mimeType ? { mimeType } : {}

  _chunks = []

  try {
    _mediaRecorder = new MediaRecorder(_stream, options)

    _mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) _chunks.push(e.data)
    }

    // 100 ms timeslice so ondataavailable fires incrementally (not just on stop)
    _mediaRecorder.start(100)
  } catch (err) {
    // Release the mic so the browser indicator clears and resources are freed
    _stream.getTracks().forEach((t) => t.stop())
    _stream = null
    _mediaRecorder = null
    _chunks = []
    throw err
  }

  return { mimeType: _mediaRecorder.mimeType }
}

/**
 * Stops the active recording and returns the collected audio as a Blob.
 * Also stops all microphone tracks so the browser indicator clears.
 * Rejects if no recording is in progress.
 */
export function stopRecording() {
  return new Promise((resolve, reject) => {
    if (!_mediaRecorder || _mediaRecorder.state === 'inactive') {
      reject(new Error('No active recording'))
      return
    }

    _mediaRecorder.onstop = () => {
      const mimeType = _mediaRecorder.mimeType
      const blob = new Blob(_chunks, { type: mimeType })
      _chunks = []

      // Release mic — done inside onstop so we don't drop the last chunk
      _stream?.getTracks().forEach((t) => t.stop())
      _stream = null
      _mediaRecorder = null

      resolve(blob)
    }

    _mediaRecorder.stop()
  })
}

/**
 * Returns true if a MediaRecorder session is currently recording.
 */
export function isRecording() {
  return _mediaRecorder?.state === 'recording'
}

/**
 * Convenience wrapper — converts a Blob to an ArrayBuffer.
 * Equivalent to blob.arrayBuffer() but keeps call sites uniform.
 */
export function blobToArrayBuffer(blob) {
  return blob.arrayBuffer()
}
