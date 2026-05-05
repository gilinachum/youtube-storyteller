import { useState, useEffect } from 'react'
import Chat from './components/Chat'
import { AUTH_MODE, getAuthInfo, login, logout, handleCallback, type AuthInfo } from './auth'

export default function App() {
  const [auth, setAuth] = useState<AuthInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [challengeUser, setChallengeUser] = useState<any>(null)

  // Handle /auth/callback (Federate mode)
  useEffect(() => {
    if (AUTH_MODE === 'federate' && window.location.pathname === '/auth/callback') {
      handleCallback()
        .then(info => {
          if (info) {
            setAuth(info)
            window.history.replaceState({}, '', '/')
          }
          setLoading(false)
        })
        .catch(e => {
          console.error(e)
          setError(e.message || 'Login failed')
          setLoading(false)
        })
      return
    }

    // Normal init — check existing auth
    getAuthInfo()
      .then(info => {
        setAuth(info)
        setLoading(false)
      })
      .catch(err => {
        console.error('Auth init failed:', err)
        setLoading(false)
      })
  }, [])

  // Federate: auto-redirect to IdP if not authenticated
  useEffect(() => {
    if (AUTH_MODE !== 'federate') return
    const inCallback = window.location.pathname === '/auth/callback'
    if (!auth && !inCallback && !loading && !error) {
      login() // redirects to Federate, never returns
    }
  }, [auth, loading, error])

  // Cognito login handler
  const handleCognitoLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const info = await login(email.trim(), password)
      setAuth(info)
    } catch (err: any) {
      if (err.message === 'NEW_PASSWORD_REQUIRED') {
        setChallengeUser(err.user)
      } else {
        setError(err.message || 'Login failed')
      }
    }
  }

  // Cognito new-password challenge
  const handleNewPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const { completeNewPassword } = await import('./auth-cognito')
      const result = await completeNewPassword(challengeUser, newPassword)
      setAuth({ email: result.email, name: result.name })
      setChallengeUser(null)
    } catch (err: any) {
      setError(err.message || 'Password change failed')
    }
  }

  const handleLogout = () => {
    logout()
    setAuth(null)
    if (AUTH_MODE === 'federate') {
      login() // redirect back to IdP
    }
  }

  // Loading state
  if (loading) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <p style={{ color: '#94a3b8' }}>
            {AUTH_MODE === 'federate' ? 'Signing you in…' : 'Loading...'}
          </p>
        </div>
      </div>
    )
  }

  // Federate error
  if (AUTH_MODE === 'federate' && error) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <h2 style={{ margin: '0 0 12px', fontSize: 18 }}>Login error</h2>
          <p style={{ color: '#fca5a5', fontSize: 14 }}>{error}</p>
          <button onClick={() => { setError(''); login() }} style={btnStyle}>
            Try again
          </button>
        </div>
      </div>
    )
  }

  // Authenticated — render chat
  if (auth) {
    return <Chat email={auth.email} onLogout={handleLogout} />
  }

  // Federate: waiting for redirect (shouldn't see this long)
  if (AUTH_MODE === 'federate') {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <p style={{ color: '#94a3b8' }}>Redirecting to sign in…</p>
        </div>
      </div>
    )
  }

  // ── Cognito: New password challenge ───────────────────────────────────────
  if (challengeUser) {
    return (
      <div style={containerStyle}>
        <form onSubmit={handleNewPassword} style={cardStyle}>
          <h1 style={{ margin: '0 0 8px', fontSize: 20 }}>StoryTeller</h1>
          <p style={{ margin: '0 0 24px', color: '#94a3b8', fontSize: 14 }}>
            Set a new password for your account.
          </p>
          {error && <p style={errorStyle}>{error}</p>}
          <input
            type="password"
            required
            autoFocus
            value={newPassword}
            onChange={e => setNewPassword(e.target.value)}
            placeholder="New password"
            style={inputStyle}
          />
          <button type="submit" style={btnStyle}>Set Password</button>
        </form>
      </div>
    )
  }

  // ── Cognito: Login form ───────────────────────────────────────────────────
  return (
    <div style={containerStyle}>
      <form onSubmit={handleCognitoLogin} style={cardStyle}>
        <h1 style={{ margin: '0 0 8px', fontSize: 20 }}>StoryTeller</h1>
        <p style={{ margin: '0 0 24px', color: '#94a3b8', fontSize: 14 }}>
          Sign in with your credentials.
        </p>
        {error && <p style={errorStyle}>{error}</p>}
        <input
          type="email"
          required
          autoFocus
          value={email}
          onChange={e => setEmail(e.target.value)}
          placeholder="you@example.com"
          style={inputStyle}
        />
        <input
          type="password"
          required
          value={password}
          onChange={e => setPassword(e.target.value)}
          placeholder="Password"
          style={inputStyle}
        />
        <button type="submit" style={btnStyle}>Sign In</button>
      </form>
    </div>
  )
}

// ── Shared styles ───────────────────────────────────────────────────────────

const containerStyle: React.CSSProperties = {
  minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
  fontFamily: 'sans-serif', background: '#0f172a', color: '#e2e8f0',
}

const cardStyle: React.CSSProperties = {
  maxWidth: 360, width: '100%', padding: 32,
  background: '#1e293b', borderRadius: 12, boxShadow: '0 10px 30px rgba(0,0,0,0.4)',
}

const inputStyle: React.CSSProperties = {
  width: '100%', padding: '10px 12px', fontSize: 14,
  borderRadius: 8, border: '1px solid #334155',
  background: '#0f172a', color: '#e2e8f0', marginBottom: 12, boxSizing: 'border-box',
}

const btnStyle: React.CSSProperties = {
  width: '100%', padding: '10px', fontSize: 14,
  borderRadius: 8, border: 'none', cursor: 'pointer',
  background: '#3b82f6', color: 'white', fontWeight: 500,
}

const errorStyle: React.CSSProperties = {
  margin: '0 0 16px', padding: '8px 12px', fontSize: 13,
  background: '#7f1d1d', borderRadius: 6, color: '#fca5a5',
}
