import type { Session } from '../api'

interface Props {
  sessions: Session[]
  currentSessionId: string | null
  onSelect: (sessionId: string) => void
  onNewChat: () => void
  email: string
  onLogout: () => void
  isOpen: boolean
  onClose: () => void
}

export default function Sidebar({ sessions, currentSessionId, onSelect, onNewChat, email, onLogout, isOpen, onClose }: Props) {
  const handleSelect = (sessionId: string) => {
    onSelect(sessionId)
    onClose() // auto-close on mobile after selecting
  }

  const handleNewChat = () => {
    onNewChat()
    onClose()
  }

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
              {sessions.map(s => (
                <button
                  key={s.session_id}
                  onClick={() => handleSelect(s.session_id)}
                  className={`w-full text-right px-3 py-2.5 rounded-xl text-sm transition-colors ${
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
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {s._shared ? `משותף ע"י ${s._shared_by}` : new Date(s.updated_at).toLocaleDateString('he-IL', { month: 'short', day: 'numeric' })}
                  </div>
                </button>
              ))}
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
