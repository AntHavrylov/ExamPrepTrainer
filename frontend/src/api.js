const TOKEN_KEY = 'prep_trainer_token'

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

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `Request failed with status ${status}`)
    this.status = status
  }
}

let unauthorizedHandler = null

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

async function request(path, { method = 'GET', body } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`

  const response = await fetch(path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  })

  if (response.status === 401) {
    setToken(null)
    unauthorizedHandler?.()
    throw new ApiError(401, 'Session expired. Please log in again.')
  }

  if (!response.ok) {
    let detail
    try {
      const data = await response.json()
      detail = typeof data.detail === 'string' ? data.detail : undefined
    } catch {
      detail = undefined
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return null
  return response.json()
}

export const api = {
  register: (email, password) =>
    request('/auth/register', { method: 'POST', body: { email, password } }),
  login: (email, password) =>
    request('/auth/login', { method: 'POST', body: { email, password } }),
  me: () => request('/auth/me'),

  listSections: () => request('/sections'),
  createSection: (name, description) =>
    request('/sections', { method: 'POST', body: { name, description: description || null } }),
  getSection: (id) => request(`/sections/${id}`),
  addDocument: (sectionId, title, content) =>
    request(`/sections/${sectionId}/documents`, { method: 'POST', body: { title, content } }),
  updateDocument: (id, title, content) =>
    request(`/documents/${id}`, { method: 'PUT', body: { title, content } }),
  deleteDocument: (id) => request(`/documents/${id}`, { method: 'DELETE' }),

  startSession: (sectionIds, mode, format) =>
    request('/sessions', { method: 'POST', body: { section_ids: sectionIds, mode, format } }),
  nextQuestion: (sessionId) => request(`/sessions/${sessionId}/next`, { method: 'POST' }),
  submitAnswer: (sessionId, payload) =>
    request(`/sessions/${sessionId}/answer`, { method: 'POST', body: payload }),
  getSession: (sessionId) => request(`/sessions/${sessionId}`),
  listSessions: () => request('/sessions'),
}
