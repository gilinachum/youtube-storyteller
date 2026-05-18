// Cognito auth — used when VITE_AUTH_MODE=cognito (dev environment).
// Uses amazon-cognito-identity-js for SRP auth (no Amplify dependency).

import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserSession,
} from 'amazon-cognito-identity-js'

const POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID || ''
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID || ''

let pool: CognitoUserPool | null = null

function getPool(): CognitoUserPool {
  if (!pool) {
    if (!POOL_ID || !CLIENT_ID) {
      throw new Error('Cognito not configured: set VITE_COGNITO_USER_POOL_ID and VITE_COGNITO_CLIENT_ID')
    }
    pool = new CognitoUserPool({ UserPoolId: POOL_ID, ClientId: CLIENT_ID })
  }
  return pool
}

export interface CognitoAuthInfo {
  email: string
  name: string
  idToken: string
}

/** Get current session if user is already signed in (from storage). */
export function getCurrentSession(): Promise<CognitoAuthInfo | null> {
  return new Promise((resolve) => {
    try {
      const user = getPool().getCurrentUser()
      if (!user) return resolve(null)
      user.getSession((err: Error | null, session: CognitoUserSession | null) => {
        if (err || !session || !session.isValid()) return resolve(null)
        resolve(extractInfo(session))
      })
    } catch {
      resolve(null)
    }
  })
}

/** Sign in with email + password. Returns auth info with tokens. */
export function signIn(email: string, password: string): Promise<CognitoAuthInfo | { newPasswordRequired: true; user: CognitoUser }> {
  return new Promise((resolve, reject) => {
    const user = new CognitoUser({ Username: email, Pool: getPool() })
    const authDetails = new AuthenticationDetails({ Username: email, Password: password })

    user.authenticateUser(authDetails, {
      onSuccess: (session) => resolve(extractInfo(session)),
      onFailure: (err) => reject(err),
      newPasswordRequired: () => resolve({ newPasswordRequired: true, user }),
    })
  })
}

/** Complete new-password challenge (first login after admin creates user). */
export function completeNewPassword(user: CognitoUser, newPassword: string): Promise<CognitoAuthInfo> {
  return new Promise((resolve, reject) => {
    user.completeNewPasswordChallenge(newPassword, {}, {
      onSuccess: (session) => resolve(extractInfo(session)),
      onFailure: (err) => reject(err),
    })
  })
}

/** Sign out — clears local storage. */
export function signOut(): void {
  try {
    const user = getPool().getCurrentUser()
    if (user) user.signOut()
  } catch { /* ignore */ }
}

/** Minimum remaining lifetime (ms) before we force-refresh the token.
 *  AgentCore rejects tokens expiring within 60s, so we refresh at 5min
 *  to give streaming requests plenty of headroom. */
const REFRESH_BUFFER_MS = 5 * 60 * 1000

/** Get a valid ID token, pre-emptively refreshing if close to expiry. */
export function getIdToken(): Promise<string | null> {
  return new Promise((resolve) => {
    try {
      const user = getPool().getCurrentUser()
      if (!user) return resolve(null)
      user.getSession((err: Error | null, session: CognitoUserSession | null) => {
        if (err || !session || !session.isValid()) return resolve(null)

        const exp = session.getIdToken().getExpiration() * 1000 // ms
        if (exp - Date.now() > REFRESH_BUFFER_MS) {
          // Token has plenty of life left — use it as-is
          return resolve(session.getIdToken().getJwtToken())
        }

        // Token expires soon — force refresh via the refresh token
        const refreshToken = session.getRefreshToken()
        user.refreshSession(refreshToken, (refreshErr: Error | null, freshSession: CognitoUserSession | null) => {
          if (refreshErr || !freshSession || !freshSession.isValid()) {
            // Refresh failed — return the (still technically valid) old token
            return resolve(session.getIdToken().getJwtToken())
          }
          resolve(freshSession.getIdToken().getJwtToken())
        })
      })
    } catch {
      resolve(null)
    }
  })
}

function extractInfo(session: CognitoUserSession): CognitoAuthInfo {
  const payload = session.getIdToken().decodePayload()
  return {
    email: payload['email'] || '',
    name: payload['name'] || payload['email']?.split('@')[0] || '',
    idToken: session.getIdToken().getJwtToken(),
  }
}
