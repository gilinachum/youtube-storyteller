import { useState, useEffect, useRef, useCallback } from 'react'
import type { Session } from '../api'

interface Props {
  sessions: Session[]
  currentSessionId: string | null
  onSelect: (sessionId: string) => void
  onNewChat: () => void
  onDelete: (sessionId: string) => void
  email: string
  onLogout: () => void
  isOpen: boolean
  onClose: () => void
}

export default function Sidebar({ sessions, currentSessionId, onSelect, onNewChat, onDelete, email, onLogout, isOpen, onClose }: Props) {
  // Track sessions pending deletion (sessionId -> timeout id)
  const [pendingDeletes, setPendingDeletes] = useState<Map<string, ReturnType<typeof setTimeout>>>(new Map())
  const pendingRef = useRef(pendingDeletes)
  pendingRef.current = pendingDeletes

  // Cleanup timers on unmount
  useEffect(() => {
    return () => {
      pendingRef.current.forEach(timer => clearTimeout(timer))
    }
  }, [])

  const handleSelect = (sessionId: string) => {
    if (pendingDeletes.has(sessionId)) return // can't select a deleting session
    onSelect(sessionId)
    onClose()
  }

  const handleNewChat = () => {
    onNewChat()
    onClose()
  }

  const handleDelete = useCallback((e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    // Start 10s timer — call onDelete after
    const timer = setTimeout(() => {
      onDelete(sessionId)
      setPendingDeletes(prev => {
        const next = new Map(prev)
        next.delete(sessionId)
        return next
      })
    }, 10000)
    setPendingDeletes(prev => new Map(prev).set(sessionId, timer))
  }, [onDelete])

  const handleUndo = useCallback((e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    const timer = pendingDeletes.get(sessionId)
    if (timer) clearTimeout(timer)
    setPendingDeletes(prev => {
      const next = new Map(prev)
      next.delete(sessionId)
      return next
    })
  }, [pendingDeletes])

  return (
    <>
      {/* Backdrop — mobile only */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar drawer */}
      <div
        className={`
          fixed top-0 right-0 h-full w-72 bg-gray-900 border-l border-gray-800 flex flex-col z-50
          transform transition-transform duration-300 ease-in-out
          ${isOpen ? 'translate-x-0' : 'translate-x-full'}
          lg:static lg:translate-x-0 lg:w-64 lg:z-auto
        `}
      >
        {/* Header */}
        <div className="p-4 border-b border-gray-800 flex items-center gap-2">
          <button
            onClick={onClose}
            className="lg:hidden p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 transition-colors"
            title="סגור"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
          <button
            onClick={handleNewChat}
            className="flex-1 py-2.5 px-4 bg-brand-600 hover:bg-brand-500 text-white font-medium rounded-xl transition-colors text-sm flex items-center justify-center gap-2"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
              <path fillRule="evenodd" d="M12 3.75a.75.75 0 01.75.75v6.75h6.75a.75.75 0 010 1.5h-6.75v6.75a.75.75 0 01-1.5 0v-6.75H4.5a.75.75 0 010-1.5h6.75V4.5a.75.75 0 01.75-.75z" clipRule="evenodd" />
            </svg>
            שיחה חדשה
          </button>
        </div>

        {/* Sessions list */}
        <div className="flex-1 overflow-y-auto scrollbar-thin p-2">
          {sessions.length === 0 ? (
            <p className="text-gray-600 text-xs text-center py-8">אין שיחות עדיין</p>
          ) : (
            <div className="space-y-1">
              {sessions.map(s => {
                const isPending = pendingDeletes.has(s.session_id)

                if (isPending) {
                  // Undo state — same rectangle, different content
                  return (
                    <div
                      key={s.session_id}
                      className="w-full px-3 py-2.5 rounded-xl text-sm bg-gray-800/50 border border-gray-700/50 flex items-center justify-between"
                    >
                      <span className="text-gray-500 text-xs">השיחה נמחקה</span>
                      <button
                        onClick={(e) => handleUndo(e, s.session_id)}
                        className="text-brand-400 hover:text-brand-300 text-xs font-medium transition-colors"
                      >
                        ביטול
                      </button>
                    </div>
                  )
                }

                return (
                  <button
                    key={s.session_id}
                    onClick={() => handleSelect(s.session_id)}
                    className={`group w-full text-right px-3 py-2.5 rounded-xl text-sm transition-colors relative ${
                      s.session_id === currentSessionId
                        ? 'bg-gray-700 text-white'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                    }`}
                  >
                    <div className="flex items-center gap-1.5">
                      <div className="font-medium truncate flex-1">{s.name || 'שיחה חדשה'}</div>
                      {(s._shared || (s.shared_with && s.shared_with.length > 0)) && (
                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-3.5 h-3.5 text-brand-400 flex-shrink-0">
                          <path d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                        </svg>
                      )}
                      {/* Delete button — visible on hover */}
                      <button
                        onClick={(e) => handleDelete(e, s.session_id)}
                        className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-gray-600 text-gray-500 hover:text-gray-300 transition-all flex-shrink-0"
                        title="מחק שיחה"
                      >
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-3.5 h-3.5">
                          <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                    <div className="text-xs text-gray-500 mt-0.5">
                      {s._shared ? `משותף ע"י ${s._shared_by}` : new Date(s.updated_at).toLocaleDateString('he-IL', { month: 'short', day: 'numeric' })}
                    </div>
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* User info */}
        <div className="p-4 border-t border-gray-800">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-full bg-brand-800 flex items-center justify-center text-sm font-medium text-brand-200 flex-shrink-0">
              {email[0]?.toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs text-gray-300 truncate" dir="ltr">{email}</p>
            </div>
            <button
              onClick={onLogout}
              className="text-gray-500 hover:text-gray-300 transition-colors flex-shrink-0"
              title="יציאה"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </>
  )
}
