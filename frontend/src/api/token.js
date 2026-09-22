// In-memory access-token holder. Never persist to localStorage/sessionStorage —
// the SPA is cookie-first (HttpOnly sd_access / sd_refresh); this is only a
// fallback for the Authorization header when LoginData.token is present.
let _token = ''

export function setToken(token) {
  _token = token || ''
}

export function getToken() {
  return _token
}

export function clearToken() {
  _token = ''
}
