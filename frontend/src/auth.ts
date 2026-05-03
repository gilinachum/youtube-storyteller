// Auth facade — delegates to either Cognito (dev) or localStorage (demo/prod).
//
// VITE_AUTH_MODE=cognito → Cognito User Pool SRP auth
// VITE_AUTH_MODE=local (default) → email in localStorage (no real auth)
//
// The Federate/CFS overlay replaces this file entirely for prod.

export const AUTH_MODE = import.meta.env.VITE_AUTH_MODE || 'local'

export interface AuthInfo {
  email: string
  name:  string
}

// ── Local (localStorage) implementation ─────────────────────────────────────

const EMAIL_KEY = 'storyteller-email'
const NAME_KEY  = 'storyteller-name'

function getLocalAuth(): AuthInfo | null {
  const email = localStorage.getItem(EMAIL_KEY)
  if (!email) return null
  return { email, name: localStorage.getItem(NAME_KEY) || email.split('@')[0] }
}

function setLocalAuth(email: string, name: string = ''): AuthInfo {
  const e = email.trim().toLowerCase()
  localStorage.setItem(EMAIL_KEY, e)
  if (name) localStorage.setItem(NAME_KEY, name)
  return { email: e, name: name || e.split('@')[0] }
}

function clearLocalAuth(): void {
  localStorage.removeItem(EMAIL_KEY)
  localStorage.removeItem(NAME_KEY)
}

// ── Exports (sync for local, async wrappers for Cognito) ────────────────────

export function getAuth(): AuthInfo | null {
  // Sync — only works for local mode. For cognito, use getAuthAsync().
  if (AUTH_MODE === 'local') return getLocalAuth()
  return null  // cognito uses async
}

export function setAuth(email: string, name: string = ''): AuthInfo {
  return setLocalAuth(email, name)
}

export function clearAuth(): void {
  if (AUTH_MODE === 'cognito') {
    import('./auth-cognito').then(m => m.signOut())
  }
  clearLocalAuth()
}

/** Async auth check — works for both modes. */
export async function getAuthAsync(): Promise<AuthInfo | null> {
  if (AUTH_MODE === 'local') return getLocalAuth()
  const { getCurrentSession } = await import('./auth-cognito')
  return getCurrentSession()
}

/** Get Authorization header value (Cognito ID token or null for local). */
export async function getAuthHeader(): Promise<string | null> {
  if (AUTH_MODE !== 'cognito') return null
  const { getIdToken } = await import('./auth-cognito')
  return getIdToken()
}
