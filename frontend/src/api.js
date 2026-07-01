const TOKEN_KEY = 'prep_trainer_token'
const REFRESH_TOKEN_KEY = 'prep_trainer_refresh_token'
export const ACTIVE_SESSION_KEY = 'prep_trainer_active_session'

// Empty by default: relative paths work as-is with the local dev proxy
// (vite.config.js) and the Nginx-proxied Docker deploy. Set at build time
// (VITE_API_BASE_URL) when the frontend and backend are on different
// origins, e.g. GitHub Pages calling an Azure-hosted backend.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

export function apiUrl(path) {
  return `${API_BASE_URL}${path}`
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY)
}

export function setToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY)
}

export function setRefreshToken(token) {
  if (token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, token)
  } else {
    localStorage.removeItem(REFRESH_TOKEN_KEY)
  }
}

export function storeTokens({ access_token, refresh_token }) {
  setToken(access_token)
  setRefreshToken(refresh_token)
}

export function clearTokens() {
  setToken(null)
  setRefreshToken(null)
}

const FIELD_LABELS = {
  content: 'Notes',
  title: 'Title',
  name: 'Name',
  description: 'Description',
  session_length: 'Session length',
  count: 'Count',
  answer: 'Answer',
  email: 'Email',
  password: 'Password',
  section_ids: 'Sections',
  selected_index: 'Answer choice',
  api_key: 'API key',
  model: 'Model',
  language: 'Language',
  mode: 'Mode',
  format: 'Format',
  difficulty: 'Difficulty',
}

function humanizeValidationErrors(errors) {
  return errors
    .map((err) => {
      const parts = Array.isArray(err.loc) ? err.loc.filter((p) => p !== 'body' && p !== 'query') : []
      const rawField = parts.length ? String(parts[parts.length - 1]) : ''
      const field = FIELD_LABELS[rawField] || rawField || 'Value'
      switch (err.type) {
        case 'string_too_long':
          return `${field} is too long (max ${Number(err.ctx?.max_length).toLocaleString()} characters)`
        case 'string_too_short':
          return err.ctx?.min_length === 1 ? `${field} cannot be empty` : `${field} is too short`
        case 'missing':
          return `${field} is required`
        case 'greater_than_equal':
          return `${field} must be at least ${err.ctx?.ge}`
        case 'less_than_equal':
          return `${field} must be at most ${err.ctx?.le}`
        case 'int_parsing':
          return `${field} must be a number`
        default:
          return err.msg || 'Invalid value'
      }
    })
    .join('; ')
}

export class ApiError extends Error {
  constructor(status, detail) {
    // `detail` may be a plain string, a Pydantic validation array, or a
    // structured object (e.g. the "no questions" guard with a `code` field).
    let message
    if (typeof detail === 'string') {
      message = detail
    } else if (Array.isArray(detail)) {
      message = humanizeValidationErrors(detail)
    } else {
      message = detail?.message || null
    }
    super(message || `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

let unauthorizedHandler = null

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

async function parseResponse(response) {
  if (!response.ok) {
    let detail
    try {
      const data = await response.json()
      detail = data.detail
    } catch {
      detail = undefined
    }
    throw new ApiError(response.status, detail)
  }
  if (response.status === 204) return null
  return response.json()
}

// Unauthenticated endpoints (register/login/refresh/logout): no Authorization
// header, and a 401 here means bad credentials/token, not an expired session,
// so it must never trigger the refresh-retry flow in `request()` below.
async function publicRequest(path, { method = 'GET', body } = {}) {
  const headers = {}
  let requestBody
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }

  const response = await fetch(apiUrl(path), { method, headers, body: requestBody })
  return parseResponse(response)
}

let refreshPromise = null

function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = publicRequest('/auth/refresh', {
      method: 'POST',
      body: { refresh_token: getRefreshToken() },
    })
      .then((tokens) => {
        storeTokens(tokens)
        return tokens
      })
      .finally(() => {
        refreshPromise = null
      })
  }
  return refreshPromise
}

async function fetchAuthenticated(path, { method = 'GET', body } = {}) {
  const headers = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  let requestBody
  if (body instanceof FormData) {
    requestBody = body
  } else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    requestBody = JSON.stringify(body)
  }

  return fetch(apiUrl(path), { method, headers, body: requestBody })
}

async function fetchWithRefresh(path, options = {}) {
  let response = await fetchAuthenticated(path, options)

  if (response.status === 401 && getRefreshToken()) {
    try {
      await refreshAccessToken()
      response = await fetchAuthenticated(path, options)
    } catch {
      // refresh failed; fall through to the 401 handling below
    }
  }

  if (response.status === 401) {
    clearTokens()
    unauthorizedHandler?.()
    throw new ApiError(401, 'Session expired. Please log in again.')
  }

  return response
}

async function request(path, options = {}) {
  const response = await fetchWithRefresh(path, options)
  return parseResponse(response)
}

function _handleSseEvent(rawEvent, onDelta) {
  const lines = rawEvent.split('\n')
  const eventLine = lines.find((line) => line.startsWith('event:'))
  const dataLine = lines.find((line) => line.startsWith('data:'))
  if (!eventLine || !dataLine) return undefined

  const eventName = eventLine.slice('event:'.length).trim()
  const data = JSON.parse(dataLine.slice('data:'.length).trim())

  if (eventName === 'delta') {
    onDelta?.(data.text)
    return undefined
  }
  if (eventName === 'error') {
    throw new ApiError(503, data.detail)
  }
  return data // the "result" event
}

// Manual fetch + stream reading instead of EventSource, since EventSource
// can't send the Authorization header this app requires for every request.
async function streamAnswer(sessionId, answerText, onDelta) {
  const response = await fetchWithRefresh(`/sessions/${sessionId}/answer/stream`, {
    method: 'POST',
    body: { answer: answerText },
  })

  if (!response.ok) {
    return parseResponse(response) // throws ApiError with the server's detail
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let result = null

  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })

    let boundary
    while ((boundary = buffer.indexOf('\n\n')) !== -1) {
      const rawEvent = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      result = _handleSseEvent(rawEvent, onDelta) ?? result
    }
  }

  return result
}

export const api = {
  register: (email, password, language) =>
    publicRequest('/auth/register', { method: 'POST', body: { email, password, language } }),
  login: (email, password) =>
    publicRequest('/auth/login', { method: 'POST', body: { email, password } }),
  logout: () => {
    const refreshToken = getRefreshToken()
    if (!refreshToken) return Promise.resolve(null)
    return publicRequest('/auth/logout', { method: 'POST', body: { refresh_token: refreshToken } })
  },
  me: () => request('/auth/me'),

  listSections: () => request('/sections'),
  createSection: (name, description) =>
    request('/sections', { method: 'POST', body: { name, description: description || null } }),
  getSection: (id) => request(`/sections/${id}`),
  deleteSection: (id) => request(`/sections/${id}`, { method: 'DELETE' }),
  addDocument: (sectionId, title, content) =>
    request(`/sections/${sectionId}/documents`, { method: 'POST', body: { title, content } }),
  uploadDocument: (sectionId, file) => {
    const formData = new FormData()
    formData.append('file', file)
    return request(`/sections/${sectionId}/documents/upload`, { method: 'POST', body: formData })
  },
  updateDocument: (id, title, content) =>
    request(`/documents/${id}`, { method: 'PUT', body: { title, content } }),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),

  startSession: (sectionIds, mode, format, difficulty, count, sectionMode) =>
    request('/sessions', {
      method: 'POST',
      body: {
        section_ids: sectionIds,
        mode,
        format,
        difficulty,
        section_mode: sectionMode ?? 'or',
        ...(count != null && { count }),
      },
    }),
  nextQuestion: (sessionId) => request(`/sessions/${sessionId}/next`, { method: 'POST' }),
  submitAnswer: (sessionId, payload) =>
    request(`/sessions/${sessionId}/answer`, { method: 'POST', body: payload }),
  streamAnswer: (sessionId, answerText, onDelta) => streamAnswer(sessionId, answerText, onDelta),
  getSession: (sessionId) => request(`/sessions/${sessionId}`),
  listSessions: () => request('/sessions'),
  getStats: () => request('/sessions/stats'),
  finishSession: (sessionId) => request(`/sessions/${sessionId}/finish`, { method: 'POST' }),

  listModels: () => request('/settings/models'),
  getApiKeyStatus: () => request('/settings/api-key'),
  saveApiKey: (apiKey, model) =>
    request('/settings/api-key', { method: 'PUT', body: { api_key: apiKey, model } }),
  updateModel: (model) =>
    request('/settings/api-key', { method: 'PATCH', body: { model } }),
  deleteApiKey: () => request('/settings/api-key', { method: 'DELETE' }),
  updateLanguage: (language) => request('/settings/language', { method: 'PUT', body: { language } }),
  updateSessionLength: (sessionLength) =>
    request('/settings/session-length', { method: 'PUT', body: { session_length: sessionLength } }),

  listQuestionBank: (filters = {}) => {
    const params = new URLSearchParams()
    Object.entries(filters).forEach(([key, value]) => {
      if (value !== undefined && value !== null && value !== '') params.set(key, value)
    })
    const query = params.toString()
    return request(`/question-bank${query ? `?${query}` : ''}`)
  },
  generateQuestionBankItems: (sectionIds, mode, format, difficulty, count) =>
    request('/question-bank/generate', {
      method: 'POST',
      body: { section_ids: sectionIds, mode, format, difficulty, count },
    }),
  getGenerationJob: (jobId) => request(`/question-bank/jobs/${jobId}`),
  deleteQuestionBankItem: (id) => request(`/question-bank/${id}`, { method: 'DELETE' }),
}
