import { useState, useEffect } from 'react'
import Chat from './components/Chat'
import { getAuthAsync, setAuth, clearAuth, AUTH_MODE, type AuthInfo } from './auth'

export default function App() {
  const [auth, setAuthState] = useState<AuthInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [error, setError] = useState('')
  const [challengeUser, setChallengeUser] = useState<any>(null)

  useEffect(() => {
    getAuthAsync().then(info => {
      setAuthState(info)
      setLoading(false)
    })
  }, [])

  const handleLocalLogin = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = email.trim()
    if (!trimmed || !trimmed.includes('@')) return
    setAuthState(setAuth(trimmed))
  }

  const handleCognitoLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const { signIn } = await import('./auth-cognito')
      const result = await signIn(email.trim(), password)
      if ('newPasswordRequired' in result) {
        setChallengeUser(result.user)
      } else {
        setAuth(result.email, result.name)
        setAuthState({ email: result.email, name: result.name })
      }
    } catch (err: any) {
      setError(err.message || 'Login failed')
    }
  }

  const handleNewPassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    try {
      const { completeNewPassword } = await import('./auth-cognito')
      const result = await completeNewPassword(challengeUser, newPassword)
      setAuth(result.email, result.name)
      setAuthState({ email: result.email, name: result.name })
      setChallengeUser(null)
    } catch (err: any) {
      setError(err.message || 'Password change failed')
    }
  }

  const handleLogout = () => {
    clearAuth()
    setAuthState(null)
  }

  if (loading) {
    return (
      <div style={containerStyle}>
        <div style={cardStyle}>
          <p style={{ color: '#94a3b8' }}>Loading...</p>
        </div>
      </div>
    )
  }

  if (auth) {
    return <Chat email={auth.email} onLogout={handleLogout} />
  }

  // ── New password challenge (first Cognito login) ──────────────────────────
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

  // ── Login form ────────────────────────────────────────────────────────────
  const isCognito = AUTH_MODE === 'cognito'

  return (
    <div style={containerStyle}>
      <form onSubmit={isCognito ? handleCognitoLogin : handleLocalLogin} style={cardStyle}>
        <h1 style={{ margin: '0 0 8px', fontSize: 20 }}>StoryTeller</h1>
        <p style={{ margin: '0 0 24px', color: '#94a3b8', fontSize: 14 }}>
          {isCognito
            ? 'Sign in with your credentials.'
            : 'Enter your email to continue. Sessions are keyed to this address.'}
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
        {isCognito && (
          <input
            type="password"
            required
            value={password}
            onChange={e => setPassword(e.target.value)}
            placeholder="Password"
            style={inputStyle}
          />
        )}
        <button type="submit" style={btnStyle}>
          {isCognito ? 'Sign In' : 'Continue'}
        </button>
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
