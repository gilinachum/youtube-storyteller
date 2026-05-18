import { useState } from 'react'

interface Props {
  onShare: (email: string) => Promise<void>
  onClose: () => void
  sharedWith: string[]
  visibility: 'private' | 'public'
  onVisibilityChange: (visibility: 'private' | 'public') => Promise<void>
  onUnshare: (email: string) => Promise<void>
  sessionId: string
}

export default function ShareModal({ onShare, onClose, sharedWith, visibility, onVisibilityChange, onUnshare, sessionId }: Props) {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [copied, setCopied] = useState(false)
  const [visLoading, setVisLoading] = useState(false)

  const shareUrl = `${window.location.origin}/s/${sessionId}`

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    const normalized = email.trim().toLowerCase()
    if (!normalized || !normalized.includes('@')) {
      setError('נדרש אימייל תקין')
      return
    }
    setLoading(true)
    setError('')
    try {
      await onShare(normalized)
      setEmail('')
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'שגיאה בשיתוף')
    } finally {
      setLoading(false)
    }
  }

  const handleVisibilityToggle = async (newVis: 'private' | 'public') => {
    if (newVis === visibility) return
    setVisLoading(true)
    try {
      await onVisibilityChange(newVis)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'שגיאה בעדכון הרשאות')
    } finally {
      setVisLoading(false)
    }
  }

  const handleCopyLink = async () => {
    try {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      // Fallback
      const input = document.createElement('input')
      input.value = shareUrl
      document.body.appendChild(input)
      input.select()
      document.execCommand('copy')
      document.body.removeChild(input)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleUnshare = async (emailToRemove: string) => {
    try {
      await onUnshare(emailToRemove)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'שגיאה בהסרת שיתוף')
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-gray-900 border border-gray-700 rounded-2xl w-full max-w-md p-6 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">שיתוף שיחה</h2>
          <button onClick={onClose} className="text-gray-400 hover:text-white transition-colors">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Visibility toggle */}
        <div className="mb-4 p-3 bg-gray-800 rounded-xl border border-gray-700">
          <p className="text-xs text-gray-400 mb-2">גישה כללית</p>
          <div className="space-y-2">
            <label className={`flex items-center gap-2 cursor-pointer p-2 rounded-lg transition-colors ${visibility === 'private' ? 'bg-gray-700' : 'hover:bg-gray-750'}`}>
              <input
                type="radio"
                name="visibility"
                checked={visibility === 'private'}
                onChange={() => handleVisibilityToggle('private')}
                disabled={visLoading}
                className="accent-brand-500"
              />
              <span className="text-sm text-gray-200">פרטי (רק אתה ומי ששיתפת)</span>
            </label>
            <label className={`flex items-center gap-2 cursor-pointer p-2 rounded-lg transition-colors ${visibility === 'public' ? 'bg-gray-700' : 'hover:bg-gray-750'}`}>
              <input
                type="radio"
                name="visibility"
                checked={visibility === 'public'}
                onChange={() => handleVisibilityToggle('public')}
                disabled={visLoading}
                className="accent-brand-500"
              />
              <span className="text-sm text-gray-200">כל מי שיש לו קישור (צפייה)</span>
            </label>
          </div>

          {/* Copy link — shown when public */}
          {visibility === 'public' && (
            <div className="mt-3 flex items-center gap-2">
              <input
                type="text"
                value={shareUrl}
                readOnly
                dir="ltr"
                className="flex-1 px-3 py-1.5 rounded-lg bg-gray-900 border border-gray-600 text-gray-300 text-xs text-left"
              />
              <button
                onClick={handleCopyLink}
                className="px-3 py-1.5 bg-brand-600 hover:bg-brand-500 text-white text-xs font-medium rounded-lg transition-colors whitespace-nowrap"
              >
                {copied ? '✓ הועתק' : 'העתק קישור'}
              </button>
            </div>
          )}
        </div>

        {/* Share by email */}
        <div className="p-3 bg-gray-800 rounded-xl border border-gray-700">
          <p className="text-xs text-gray-400 mb-2">שיתוף לפי אימייל</p>
          <form onSubmit={handleSubmit} className="space-y-3">
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="הזן אימייל לשיתוף..."
              dir="ltr"
              className="w-full px-4 py-2.5 rounded-xl bg-gray-900 border border-gray-700 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500 text-sm text-left"
            />
            {error && <p className="text-red-400 text-xs">{error}</p>}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 bg-brand-600 hover:bg-brand-500 disabled:bg-gray-700 text-white font-medium rounded-xl transition-colors text-sm"
            >
              {loading ? 'משתף...' : 'שתף'}
            </button>
          </form>

          {/* Currently shared with */}
          {sharedWith.length > 0 && (
            <div className="mt-3 pt-3 border-t border-gray-700">
              <p className="text-xs text-gray-500 mb-2">משותף עם:</p>
              <div className="space-y-1">
                {sharedWith.map(e => (
                  <div key={e} className="flex items-center gap-2 px-3 py-1.5 bg-gray-900 rounded-lg text-sm text-gray-300" dir="ltr">
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-brand-400 shrink-0">
                      <path fillRule="evenodd" d="M7.5 6a4.5 4.5 0 119 0 4.5 4.5 0 01-9 0zM3.751 20.105a8.25 8.25 0 0116.498 0 .75.75 0 01-.437.695A18.683 18.683 0 0112 22.5c-2.786 0-5.433-.608-7.812-1.7a.75.75 0 01-.437-.695z" clipRule="evenodd" />
                    </svg>
                    <span className="flex-1">{e}</span>
                    <button
                      onClick={() => handleUnshare(e)}
                      className="p-0.5 rounded hover:bg-gray-700 text-gray-500 hover:text-red-400 transition-colors"
                      title="הסר שיתוף"
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-3.5 h-3.5">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                      </svg>
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
