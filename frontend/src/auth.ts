// Minimal identity — no auth. User types their email once; it's stored
// in localStorage and passed to API calls as a query/body field. This is
// fine for demos and solo use.
//
// For production / multi-user deployments, replace this with a real
// auth provider (Cognito, Auth0, OIDC, etc.) and call a backend
// authorizer on every API request.

const EMAIL_KEY = 'storyteller-email'
const NAME_KEY  = 'storyteller-name'

export interface AuthInfo {
  email: string
  name:  string
}

export function getAuth(): AuthInfo | null {
  const email = localStorage.getItem(EMAIL_KEY)
  if (!email) return null
  return { email, name: localStorage.getItem(NAME_KEY) || email.split('@')[0] }
}

export function setAuth(email: string, name: string = ''): AuthInfo {
  const e = email.trim().toLowerCase()
  localStorage.setItem(EMAIL_KEY, e)
  if (name) localStorage.setItem(NAME_KEY, name)
  return { email: e, name: name || e.split('@')[0] }
}

export function clearAuth(): void {
  localStorage.removeItem(EMAIL_KEY)
  localStorage.removeItem(NAME_KEY)
}
