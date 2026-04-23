import { useState, useEffect } from 'react'
import Login from './components/Login'
import Chat from './components/Chat'
import { getStoredTokens, clearTokens } from './cognito'

export default function App() {
  const [email, setEmail] = useState<string | null>(() => {
    return getStoredTokens()?.email ?? null
  })

  const handleAuth = (email: string) => {
    setEmail(email)
  }

  const handleLogout = () => {
    clearTokens()
    setEmail(null)
  }

  // Check token validity on focus (returning to tab)
  useEffect(() => {
    const checkTokens = () => {
      if (email && !getStoredTokens()) {
        // Token expired and refresh failed — force re-login
        setEmail(null)
      }
    }
    window.addEventListener('focus', checkTokens)
    return () => window.removeEventListener('focus', checkTokens)
  }, [email])

  if (!email) {
    return <Login onAuth={handleAuth} />
  }

  return <Chat email={email} onLogout={handleLogout} />
}
