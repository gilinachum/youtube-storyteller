// Cognito authentication helper — uses USER_PASSWORD_AUTH flow directly
// No SDK dependency needed

const _COGNITO_REGION = import.meta.env.VITE_COGNITO_REGION || 'us-east-1'
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || ''

const COGNITO_ENDPOINT = `https://cognito-idp.${_COGNITO_REGION}.amazonaws.com/`

export interface CognitoTokens {
  idToken: string
  accessToken: string
  refreshToken: string
  expiresAt: number // unix ms
  email: string
}

const STORAGE_KEY = 'storyteller-cognito'

export function getStoredTokens(): CognitoTokens | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (!stored) return null
    const tokens: CognitoTokens = JSON.parse(stored)
    // Check if expired (with 5min buffer)
    if (tokens.expiresAt < Date.now() + 5 * 60 * 1000) {
      return null // Treat as expired — caller should refresh
    }
    return tokens
  } catch {
    return null
  }
}

export function storeTokens(tokens: CognitoTokens): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(tokens))
  // Set auth cookie for CloudFront media access (HttpOnly not possible from JS,
  // but Secure + SameSite=Lax protects against cross-site attacks)
  const maxAge = Math.floor((tokens.expiresAt - Date.now()) / 1000)
  document.cookie = `st-auth=${tokens.idToken}; path=/media; max-age=${maxAge}; secure; samesite=lax`
}

export function clearTokens(): void {
  localStorage.removeItem(STORAGE_KEY)
  document.cookie = 'st-auth=; path=/media; max-age=0; secure; samesite=lax'
}

export function getIdToken(): string | null {
  return getStoredTokens()?.idToken ?? null
}

async function cognitoRequest(action: string, payload: Record<string, unknown>): Promise<any> {
  const res = await fetch(COGNITO_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-amz-json-1.1',
      'X-Amz-Target': `AWSCognitoIdentityProviderService.${action}`,
    },
    body: JSON.stringify(payload),
  })

  const data = await res.json()

  if (!res.ok) {
    const errorType = data.__type?.split('#').pop() || 'UnknownError'
    const errorMsg = data.message || data.Message || 'Authentication failed'
    throw new CognitoError(errorType, errorMsg)
  }

  return data
}

export class CognitoError extends Error {
  type: string
  constructor(type: string, message: string) {
    super(message)
    this.type = type
    this.name = 'CognitoError'
  }
}

/**
 * Sign in with email + password.
 * Returns tokens or throws CognitoError.
 * Handles NEW_PASSWORD_REQUIRED challenge for first-time users.
 */
export async function signIn(email: string, password: string): Promise<CognitoTokens> {
  const data = await cognitoRequest('InitiateAuth', {
    AuthFlow: 'USER_PASSWORD_AUTH',
    ClientId: CLIENT_ID,
    AuthParameters: {
      USERNAME: email,
      PASSWORD: password,
    },
  })

  // Handle first-login password change challenge
  if (data.ChallengeName === 'NEW_PASSWORD_REQUIRED') {
    // Automatically respond with the same password
    const challengeData = await cognitoRequest('RespondToAuthChallenge', {
      ChallengeName: 'NEW_PASSWORD_REQUIRED',
      ClientId: CLIENT_ID,
      Session: data.Session,
      ChallengeResponses: {
        USERNAME: email,
        NEW_PASSWORD: password,
      },
    })
    return parseAuthResult(challengeData.AuthenticationResult, email)
  }

  if (!data.AuthenticationResult) {
    throw new CognitoError('NoResult', 'No authentication result returned')
  }

  return parseAuthResult(data.AuthenticationResult, email)
}

/**
 * Refresh tokens using the refresh token.
 */
export async function refreshTokens(refreshToken: string, email: string): Promise<CognitoTokens> {
  const data = await cognitoRequest('InitiateAuth', {
    AuthFlow: 'REFRESH_TOKEN_AUTH',
    ClientId: CLIENT_ID,
    AuthParameters: {
      REFRESH_TOKEN: refreshToken,
    },
  })

  if (!data.AuthenticationResult) {
    throw new CognitoError('NoResult', 'Token refresh failed')
  }

  // Refresh flow doesn't return a new refresh token — keep the old one
  const tokens = parseAuthResult(data.AuthenticationResult, email)
  tokens.refreshToken = refreshToken
  return tokens
}

/**
 * Get a valid ID token, refreshing if needed.
 */
export async function getValidIdToken(): Promise<string> {
  const stored = getStoredTokens()
  if (stored) return stored.idToken

  // Try to refresh
  const raw = localStorage.getItem(STORAGE_KEY)
  if (raw) {
    try {
      const old: CognitoTokens = JSON.parse(raw)
      if (old.refreshToken) {
        const refreshed = await refreshTokens(old.refreshToken, old.email)
        storeTokens(refreshed)
        return refreshed.idToken
      }
    } catch {
      // Refresh failed — user needs to re-login
    }
  }

  clearTokens()
  throw new CognitoError('TokenExpired', 'Session expired. Please sign in again.')
}

function parseAuthResult(result: any, email: string): CognitoTokens {
  const tokens: CognitoTokens = {
    idToken: result.IdToken,
    accessToken: result.AccessToken,
    refreshToken: result.RefreshToken || '',
    expiresAt: Date.now() + (result.ExpiresIn || 3600) * 1000,
    email,
  }
  storeTokens(tokens)
  return tokens
}
