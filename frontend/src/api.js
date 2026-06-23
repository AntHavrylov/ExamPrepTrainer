const TOKEN_KEY = 'prep_trainer_token'
const REFRESH_TOKEN_KEY = 'prep_trainer_refresh_token'

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

async function parseResponse(response) {
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

  const response = await fetch(path, { method, headers, body: requestBody })
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

  return fetch(path, { method, headers, body: requestBody })
}

async function request(path, options = {}) {
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

  return parseResponse(response)
}

export const api = {
  register: (email, password) =>
    publicRequest('/auth/register', { method: 'POST', body: { email, password } }),
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

  startSession: (sectionIds, mode, format) =>
    request('/sessions', { method: 'POST', body: { section_ids: sectionIds, mode, format } }),
  nextQuestion: (sessionId) => request(`/sessions/${sessionId}/next`, { method: 'POST' }),
  submitAnswer: (sessionId, payload) =>
    request(`/sessions/${sessionId}/answer`, { method: 'POST', body: payload }),
  getSession: (sessionId) => request(`/sessions/${sessionId}`),
  listSessions: () => request('/sessions'),
}
