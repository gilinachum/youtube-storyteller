import { useState } from 'react'
import Chat from './components/Chat'
import { getAuth, setAuth, clearAuth, type AuthInfo } from './auth'

export default function App() {
  const [auth, setAuthState] = useState<AuthInfo | null>(() => getAuth())
  const [input, setInput]    = useState<string>('')

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault()
    const email = input.trim()
    if (!email || !email.includes('@')) return
    setAuthState(setAuth(email))
  }

  const handleLogout = () => {
    clearAuth()
    setAuthState(null)
  }

  if (!auth) {
    return (
      <div style={{
        minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontFamily: 'sans-serif', background: '#0f172a', color: '#e2e8f0',
      }}>
        <form onSubmit={handleLogin} style={{
          maxWidth: 360, width: '100%', padding: 32,
          background: '#1e293b', borderRadius: 12, boxShadow: '0 10px 30px rgba(0,0,0,0.4)',
        }}>
          <h1 style={{margin: '0 0 8px', fontSize: 20}}>StoryTeller</h1>
          <p style={{margin: '0 0 24px', color: '#94a3b8', fontSize: 14}}>
            Enter your email to continue. Sessions are keyed to this address.
          </p>
          <input
            type="email"
            required
            autoFocus
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="you@example.com"
            style={{
              width: '100%', padding: '10px 12px', fontSize: 14,
              borderRadius: 8, border: '1px solid #334155',
              background: '#0f172a', color: '#e2e8f0', marginBottom: 12, boxSizing: 'border-box',
            }}
          />
          <button type="submit" style={{
            width: '100%', padding: '10px', fontSize: 14,
            borderRadius: 8, border: 'none', cursor: 'pointer',
            background: '#3b82f6', color: 'white', fontWeight: 500,
          }}>Continue</button>
        </form>
      </div>
    )
  }

  return <Chat email={auth.email} onLogout={handleLogout} />
}
