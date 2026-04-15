export const CAMERA_TRIGGER_KEYWORDS = [
  'photo',
  'picture',
  'image',
  'skin',
  'wound',
  'rash',
  'redness',
  'swelling',
  'bruise',
  'sore',
  'lesion',
  'medication',
  'pill',
  'bottle',
  'prescription',
  'insurance card',
  'id card',
]

const PROMPT_MAP = {
  skin:             'Please take a clear photo of the affected skin area.',
  wound:            'Please take a photo of the wound or injury.',
  rash:             'Please take a close-up photo of the rash.',
  redness:          'Please take a photo showing the area of redness.',
  swelling:         'Please photograph the swollen area.',
  bruise:           'Please photograph the bruise.',
  sore:             'Please photograph the sore.',
  lesion:           'Please photograph the lesion.',
  medication:       'Please take a photo of your medication bottle or pill.',
  pill:             'Please take a photo of the pill.',
  bottle:           'Please take a photo of the medication bottle label.',
  prescription:     'Please photograph your prescription label.',
  'insurance card': 'Please take a clear photo of your insurance card.',
  'id card':        'Please take a photo of your ID card.',
  photo:            'Please take a photo as requested.',
  picture:          'Please take a photo as requested.',
  image:            'Please take a photo as requested.',
}

/**
 * Returns true if the question text contains any camera trigger keyword.
 * Case-insensitive substring match.
 *
 * @param {string} questionText
 * @returns {boolean}
 */
export function requiresCamera(questionText) {
  if (!questionText || typeof questionText !== 'string') return false
  const lower = questionText.toLowerCase()
  return CAMERA_TRIGGER_KEYWORDS.some((kw) => lower.includes(kw))
}

/**
 * Returns a contextual prompt string for the CameraCapture modal header.
 * Used as a fallback when the backend does not yet supply image_prompt.
 *
 * @param {string} questionText
 * @returns {string}
 */
export function getCameraPrompt(questionText) {
  if (!questionText || typeof questionText !== 'string') return 'Please take a photo.'
  const lower = questionText.toLowerCase()
  const match = Object.keys(PROMPT_MAP).find((kw) => lower.includes(kw))
  return match ? PROMPT_MAP[match] : 'Please take a photo related to this question.'
}
