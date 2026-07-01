// Unified auth module — switches between Cognito (dev) and Federate OIDC (prod)
// based on VITE_AUTH_MODE environment variable.
//
// VITE_AUTH_MODE=cognito  → Cognito User Pool SRP auth (delegates to ./auth-cognito.ts)
// VITE_AUTH_MODE=federate → PKCE/OIDC flow with Federate IdP

export const AUTH_MODE = import.meta.env.VITE_AUTH_MODE || 'cognito'

export interface AuthInfo {
  email: string
  name: string
}

// ─── Federate OIDC config ───────────────────────────────────────────────────
const FEDERATE_AUTHORIZE_URL = import.meta.env.VITE_FEDERATE_AUTHORIZE_URL || ''
const FEDERATE_CLIENT_ID = import.meta.env.VITE_FEDERATE_CLIENT_ID || ''
const FEDERATE_REDIRECT_URI = import.meta.env.VITE_FEDERATE_REDIRECT_URI || `${window.location.origin}/auth/callback`
const FEDERATE_SCOPES = import.meta.env.VITE_FEDERATE_SCOPES || 'openid'

// Federate sessionStorage keys
const TOKEN_KEY = 'storyteller-id-token'
const EXPIRY_KEY = 'storyteller-token-expiry'
const EMAIL_KEY = 'storyteller-email'
const NAME_KEY = 'storyteller-name'
const REFRESH_KEY = 'storyteller-refresh-token'
const PKCE_KEY = 'storyteller-pkce-verifier'
const STATE_KEY = 'storyteller-oauth-state'

// Refresh buffer: refresh 2 minutes before expiry to avoid any disruption
const REFRESH_BUFFER_MS = 2 * 60 * 1000
// Track in-flight refresh to avoid duplicate requests
let _refreshPromise: Promise<boolean> | null = null
let _refreshTimer: ReturnType<typeof setTimeout> | null = null

// ─── PKCE helpers ───────────────────────────────────────────────────────────
function base64urlEncode(bytes: Uint8Array): string {
  return btoa(String.fromCharCode(...bytes))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')
}

function randomBytes(n: number): Uint8Array {
  const buf = new Uint8Array(n)
  crypto.getRandomValues(buf)
  return buf
}

async function sha256(s: string): Promise<Uint8Array> {
  const data = new TextEncoder().encode(s)
  const digest = await crypto.subtle.digest('SHA-256', data)
  return new Uint8Array(digest)
}

// ─── JWT decode (no verification — Lambda authorizer does that) ─────────────
function decodeIdToken(idToken: string): { email: string; name: string; exp: number } {
  const [, payloadB64] = idToken.split('.')
  let b64 = payloadB64.replace(/-/g, '+').replace(/_/g, '/')
  while (b64.length % 4) b64 += '='
  const payload = JSON.parse(atob(b64))
  return {
    email: (payload.email || '').toLowerCase(),
    name: payload.name || '',
    exp: (payload.exp || 0) * 1000,
  }
}

// ─── Federate internal helpers ──────────────────────────────────────────────
function getFederateAuth(): AuthInfo | null {
  const idToken = sessionStorage.getItem(TOKEN_KEY)
  const expiry = parseInt(sessionStorage.getItem(EXPIRY_KEY) || '0', 10)
  if (!idToken || !expiry) return null
  // Token completely expired (past expiry) — clear
  if (expiry < Date.now()) {
    clearFederateAuth()
    return null
  }
  // Token still valid — trigger background refresh if close to expiry
  if (expiry < Date.now() + REFRESH_BUFFER_MS) {
    silentRefresh() // fire-and-forget
  } else if (!_refreshTimer) {
    // Schedule proactive refresh for later
    scheduleRefresh(expiry)
  }
  return {
    email: sessionStorage.getItem(EMAIL_KEY) || '',
    name: sessionStorage.getItem(NAME_KEY) || '',
  }
}

function clearFederateAuth(): void {
  sessionStorage.removeItem(TOKEN_KEY)
  sessionStorage.removeItem(EXPIRY_KEY)
  sessionStorage.removeItem(EMAIL_KEY)
  sessionStorage.removeItem(NAME_KEY)
  sessionStorage.removeItem(REFRESH_KEY)
  if (_refreshTimer) {
    clearTimeout(_refreshTimer)
    _refreshTimer = null
  }
}

function getFederateToken(): string | null {
  const idToken = sessionStorage.getItem(TOKEN_KEY)
  const expiry = parseInt(sessionStorage.getItem(EXPIRY_KEY) || '0', 10)
  if (!idToken || !expiry) return null
  // Token completely expired
  if (expiry < Date.now()) {
    clearFederateAuth()
    return null
  }
  // Trigger background refresh if close to expiry
  if (expiry < Date.now() + REFRESH_BUFFER_MS) {
    silentRefresh() // fire-and-forget
  }
  return idToken
}

/**
 * Silently refresh the id_token using the stored refresh_token.
 * Returns true if refresh succeeded, false otherwise.
 * Deduplicates concurrent calls.
 */
async function silentRefresh(): Promise<boolean> {
  if (_refreshPromise) return _refreshPromise

  _refreshPromise = (async () => {
    const refreshToken = sessionStorage.getItem(REFRESH_KEY)
    if (!refreshToken) return false

    try {
      const res = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      })

      if (!res.ok) {
        // Refresh token rejected (expired/revoked) — force re-auth
        clearFederateAuth()
        return false
      }

      const data = await res.json() as {
        id_token: string
        expires_in: number
        refresh_token?: string
      }
      if (!data.id_token) {
        clearFederateAuth()
        return false
      }

      const claims = decodeIdToken(data.id_token)
      const expiresAt = claims.exp || (Date.now() + data.expires_in * 1000)

      sessionStorage.setItem(TOKEN_KEY, data.id_token)
      sessionStorage.setItem(EXPIRY_KEY, String(expiresAt))
      sessionStorage.setItem(EMAIL_KEY, claims.email)
      sessionStorage.setItem(NAME_KEY, claims.name)
      if (data.refresh_token) {
        sessionStorage.setItem(REFRESH_KEY, data.refresh_token)
      }

      // Schedule next refresh
      scheduleRefresh(expiresAt)
      return true
    } catch {
      // Network failure — schedule a retry in 30s
      if (_refreshTimer) clearTimeout(_refreshTimer)
      _refreshTimer = setTimeout(() => { silentRefresh() }, 30_000)
      return false
    }
  })().finally(() => { _refreshPromise = null })

  return _refreshPromise
}

/** Schedule a proactive refresh 2 minutes before the token expires. */
function scheduleRefresh(expiresAt: number): void {
  if (_refreshTimer) clearTimeout(_refreshTimer)
  const delay = Math.max(expiresAt - Date.now() - REFRESH_BUFFER_MS, 10_000)
  _refreshTimer = setTimeout(() => { silentRefresh() }, delay)
}

// ─── Public API ─────────────────────────────────────────────────────────────

/** Get current auth token (JWT) for Authorization header. */
export async function getToken(): Promise<string | null> {
  if (AUTH_MODE === 'federate') {
    return getFederateToken()
  }
  // Cognito mode
  const { getIdToken } = await import('./auth-cognito')
  return getIdToken()
}

/** Alias for getToken — kept for backward compat with federate code. */
export async function getIdToken(): Promise<string | null> {
  return getToken()
}

/** Get current auth info (email + name) if authenticated. */
export async function getAuthInfo(): Promise<AuthInfo | null> {
  if (AUTH_MODE === 'federate') {
    return getFederateAuth()
  }
  // Cognito mode
  const { getCurrentSession } = await import('./auth-cognito')
  return getCurrentSession()
}

/**
 * Initiate login.
 * - Cognito: signs in with email + password, returns AuthInfo.
 * - Federate: redirects to IdP (never returns).
 */
export async function login(email?: string, password?: string): Promise<AuthInfo> {
  if (AUTH_MODE === 'federate') {
    // Generate PKCE verifier + challenge + state
    const verifier = base64urlEncode(randomBytes(48))
    const challenge = base64urlEncode(await sha256(verifier))
    const state = base64urlEncode(randomBytes(16))

    sessionStorage.setItem(PKCE_KEY, verifier)
    sessionStorage.setItem(STATE_KEY, state)

    const params = new URLSearchParams({
      response_type: 'code',
      client_id: FEDERATE_CLIENT_ID,
      redirect_uri: FEDERATE_REDIRECT_URI,
      scope: FEDERATE_SCOPES,
      state,
      code_challenge: challenge,
      code_challenge_method: 'S256',
    })

    window.location.assign(`${FEDERATE_AUTHORIZE_URL}?${params}`)
    // Unreachable — redirect happens
    return new Promise<AuthInfo>(() => {})
  }

  // Cognito mode
  if (!email || !password) throw new Error('Email and password required for Cognito login')
  const { signIn } = await import('./auth-cognito')
  const result = await signIn(email, password)
  if ('newPasswordRequired' in result) {
    throw Object.assign(new Error('NEW_PASSWORD_REQUIRED'), { user: result.user })
  }
  return { email: result.email, name: result.name }
}

/** Sign out and clear all stored auth state. */
export function logout(): void {
  if (AUTH_MODE === 'federate') {
    clearFederateAuth()
    return
  }
  // Cognito mode
  import('./auth-cognito').then(m => m.signOut())
}

/**
 * Handle the /auth/callback redirect (Federate mode only).
 * Parses ?code=..., exchanges for tokens via backend, stores, returns AuthInfo.
 */
export async function handleCallback(): Promise<AuthInfo | null> {
  if (AUTH_MODE !== 'federate') return null

  const url = new URL(window.location.href)
  const code = url.searchParams.get('code')
  const state = url.searchParams.get('state')
  const error = url.searchParams.get('error')

  if (error) {
    throw new Error(`Federate error: ${error} — ${url.searchParams.get('error_description') || ''}`)
  }
  if (!code || !state) {
    throw new Error('Missing code or state in callback URL')
  }

  const savedState = sessionStorage.getItem(STATE_KEY)
  const codeVerifier = sessionStorage.getItem(PKCE_KEY)
  if (state !== savedState || !codeVerifier) {
    throw new Error('Invalid OAuth state (possible CSRF)')
  }

  // Exchange code for tokens via the backend (client_secret is server-side)
  const res = await fetch('/api/auth/callback', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      code,
      code_verifier: codeVerifier,
      redirect_uri: FEDERATE_REDIRECT_URI,
    }),
  })

  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Token exchange failed (${res.status}): ${text}`)
  }
  const data = await res.json() as { id_token: string; expires_in: number; refresh_token?: string }
  if (!data.id_token) {
    throw new Error('No id_token in response')
  }

  const claims = decodeIdToken(data.id_token)
  const expiresAt = claims.exp || (Date.now() + data.expires_in * 1000)

  sessionStorage.setItem(TOKEN_KEY, data.id_token)
  sessionStorage.setItem(EXPIRY_KEY, String(expiresAt))
  sessionStorage.setItem(EMAIL_KEY, claims.email)
  sessionStorage.setItem(NAME_KEY, claims.name)
  if (data.refresh_token) {
    sessionStorage.setItem(REFRESH_KEY, data.refresh_token)
  }

  // Schedule proactive background refresh
  scheduleRefresh(expiresAt)

  // Clean up one-shot values
  sessionStorage.removeItem(PKCE_KEY)
  sessionStorage.removeItem(STATE_KEY)

  return { email: claims.email, name: claims.name }
}

/**
 * Ensure there's a valid auth. If not, redirect to login (federate) or throw (cognito).
 */
export async function requireAuth(): Promise<AuthInfo> {
  const info = await getAuthInfo()
  if (info) return info
  if (AUTH_MODE === 'federate') {
    await login()
    // login() redirects, unreachable
    throw new Error('unreachable')
  }
  throw new Error('Not authenticated')
}
