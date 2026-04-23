import { useState } from 'react'
import { signIn, CognitoError } from '../cognito'

interface Props {
  onAuth: (email: string) => void
}

const ERROR_MESSAGES: Record<string, string> = {
  NotAuthorizedException: 'אימייל או סיסמה שגויים',
  UserNotFoundException: 'משתמש לא נמצא',
  UserNotConfirmedException: 'המשתמש לא מאושר',
  PasswordResetRequiredException: 'נדרש איפוס סיסמה',
  InvalidParameterException: 'פרטים לא תקינים',
  TokenExpired: 'תוקף הסשן פג, נא להתחבר מחדש',
}

export default function Login({ onAuth }: Props) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    const normalizedEmail = email.trim().toLowerCase()
    if (!normalizedEmail.includes('@')) {
      setError('נדרש אימייל תקין')
      return
    }
    if (!password) {
      setError('נדרשת סיסמה')
      return
    }

    setLoading(true)
    try {
      await signIn(normalizedEmail, password)
      onAuth(normalizedEmail)
    } catch (err: unknown) {
      if (err instanceof CognitoError) {
        setError(ERROR_MESSAGES[err.type] || err.message)
      } else {
        setError(err instanceof Error ? err.message : 'שגיאה בהתחברות')
      }
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-brand-600 mb-4">
            <span className="text-3xl">🎬</span>
          </div>
          <h1 className="text-3xl font-bold text-white">StoryTeller</h1>
          <p className="text-gray-400 mt-2">תכנון סרטוני YouTube עם AI</p>
        </div>

        {/* Login card */}
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-xl">
          <h2 className="text-xl font-semibold text-white mb-6 text-center">כניסה למערכת</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-gray-300 mb-2">
                אימייל
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                placeholder="your@email.com"
                dir="ltr"
                className="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition text-left"
                required
                autoComplete="email"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-gray-300 mb-2">
                סיסמה
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="••••••••"
                dir="ltr"
                className="w-full px-4 py-3 rounded-xl bg-gray-800 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent transition text-left"
                required
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className="bg-red-900/30 border border-red-700 rounded-xl px-4 py-3 text-red-300 text-sm">
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full py-3 px-4 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 disabled:cursor-not-allowed text-white font-semibold rounded-xl transition-colors"
            >
              {loading ? 'מתחבר...' : 'כניסה'}
            </button>
          </form>

          <p className="text-gray-500 text-xs text-center mt-6">
            גישה מוגבלת למשתמשים מורשים בלבד
          </p>
        </div>
      </div>
    </div>
  )
}
