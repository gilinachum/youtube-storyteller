import { useState, useCallback, useEffect, useRef } from 'react'
import { streamChat, listSessions, getSessionMessages, uploadFile, shareSession, getFileDownloadUrl, transcribeAudio, deleteSession, setSessionVisibility, unshareSession } from '../api'
import { useJobPolling } from '../hooks/useJobPolling'
import type { Session, FileRecord } from '../api'
import ChatMessages from './ChatMessages'
import ChatInput from './ChatInput'
import type { UploadedFile } from './ChatInput'
import Sidebar from './Sidebar'
import ShareModal from './ShareModal'
import FileList from './FileList'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

interface Props {
  email: string
  onLogout: () => void
  initialSessionId?: string
}

const WELCOME_MESSAGE: Message = {
  id: 'welcome',
  role: 'assistant',
  content: `אני StoryTeller 🎬 — מומחה תכנון תוכן טכנולוגי.

**מה אני יודע לעשות:**

✍️ **לתכנן תוכן** — סרטוני YouTube, הרצאות, ראיונות, וורקשופים

📺 **לצפות בסרטוני YouTube קיימים** — תן לי לינק ואנתח מבנה, סגנון, קהל, וזוויות תוכן

🔍 **לחקור נושאים לעומק** — חיפוש אינטרנט, טרנדים, וניתוח סרטונים מתחרים

🎨 **לעצב באנר או טאמבנייל** — עיצוב איטרטיבי כולל תמונת הפרפיל שלך וסגנון מותאם

📄 **לעבד חומרי גלם** — PDF, מצגות, הקלטות וידיאו/אודיו, URLs

📋 **לייצא מסמך להורדה** — מתכנון בראשי פרקים ועד לסקריפט מושלם

🔲 **לייצר QR Code** — תן לי URL ואייצר קוד QR להורדה ושיתוף

⚠️ **שים לב:** השתמש ב-StoryTeller עם מידע פומבי בלבד. אין להזין מידע סודי, פנימי, או נתוני לקוחות.

מה בראש שלך? 🚀`,
  timestamp: Date.now(),
}

export default function Chat({ email, onLogout, initialSessionId }: Props) {
  const [messages, setMessages] = useState<Message[]>([WELCOME_MESSAGE])
  const [sessions, setSessions] = useState<Session[]>([])
  const [currentSessionId, setCurrentSessionId] = useState<string>(() => {
    // Restore last active session or create new
    const saved = localStorage.getItem(`storyteller-last-session-${email}`)
    return saved || crypto.randomUUID()
  })
  const [loading, setLoading] = useState(false)
  const [streamingContent, setStreamingContent] = useState('')
  const [progressLabel, setProgressLabel] = useState('')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [sessionFiles, setSessionFiles] = useState<FileRecord[]>([])
  const [showShareModal, setShowShareModal] = useState(false)
  const [showFiles, setShowFiles] = useState(false)
  const [sharedWith, setSharedWith] = useState<string[]>([])
  const [isSharedSession, setIsSharedSession] = useState(false)
  const [access, setAccess] = useState<'owner' | 'collaborator' | 'viewer'>('owner')
  const [visibility, setVisibility] = useState<'private' | 'public'>('private')
  const abortControllerRef = useRef<AbortController | null>(null)
  // Stable ref so handleSend's onDone closure can call checkNow without stale captures
  const checkNowRef = useRef<() => Promise<void>>(() => Promise.resolve())
  // Stable ref so handleJobsReady can call handleSend without circular hook deps
  const handleSendRef = useRef<(text: string, files?: UploadedFile[]) => Promise<void>>(() => Promise.resolve())

  // Persist current session ID
  useEffect(() => {
    localStorage.setItem(`storyteller-last-session-${email}`, currentSessionId)
  }, [email, currentSessionId])

  // URL routing: update URL on session changes
  const updateUrl = useCallback((sessionId: string | null) => {
    if (sessionId) {
      window.history.pushState({}, '', '/s/' + sessionId)
    } else {
      window.history.pushState({}, '', '/')
    }
  }, [])

  // Refs for popstate — avoids stale closure over currentSessionId/callbacks
  const currentSessionIdRef = useRef(currentSessionId)
  useEffect(() => { currentSessionIdRef.current = currentSessionId }, [currentSessionId])
  const handleSelectSessionRef = useRef<(sid: string) => void>(() => {})
  const handleNewChatRef = useRef<() => void>(() => {})

  // Listen to popstate for browser back/forward
  useEffect(() => {
    const handlePopState = () => {
      const match = window.location.pathname.match(/^\/s\/([\w-]+)/)
      if (match) {
        const sid = match[1]
        if (sid !== currentSessionIdRef.current) {
          handleSelectSessionRef.current(sid)
        }
      } else {
        handleNewChatRef.current()
      }
    }
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])  // stable — uses refs

  // Load sessions on mount + restore last session or initialSessionId
  useEffect(() => {
    listSessions().then(sessions => {
      setSessions(sessions)
      // Priority: initialSessionId (from URL) > saved session
      const targetId = initialSessionId || localStorage.getItem(`storyteller-last-session-${email}`)
      if (targetId) {
        // For initialSessionId, always try to load (might be a public session not in our list)
        const inList = sessions.some(s => s.session_id === targetId)
        if (inList || initialSessionId) {
          getSessionMessages(targetId)
            .then(data => {
              if (data.messages && data.messages.length > 0) {
                const loaded: Message[] = data.messages.map((m: any, i: number) => ({
                  id: `restored-${i}`,
                  role: m.role as 'user' | 'assistant',
                  content: m.content,
                  timestamp: new Date(m.timestamp).getTime(),
                }))
                setMessages([{ ...WELCOME_MESSAGE, id: 'welcome', timestamp: 0 }, ...loaded])
                setCurrentSessionId(targetId)
                if (data.files) setSessionFiles(data.files)
                if (data.shared_with) setSharedWith(data.shared_with)
                if (data.access) setAccess(data.access)
                if (data.visibility) setVisibility(data.visibility)
                // Update URL to reflect the session
                window.history.replaceState({}, '', '/s/' + targetId)
              }
            })
            .catch(console.error)
        }
      }
    }).catch(console.error)
  }, [email])

  // Auto-recover on tab focus — reload session messages if stream was interrupted
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && !loading) {
        // Reload current session messages to get the full response
        getSessionMessages(currentSessionId)
          .then(data => {
            if (data.messages && data.messages.length > 0) {
              const loaded: Message[] = data.messages.map((m: any, i: number) => ({
                id: `loaded-${i}`,
                role: m.role as 'user' | 'assistant',
                content: m.content,
                timestamp: new Date(m.timestamp).getTime(),
              }))
              // Only update if server has more messages than we have (excluding welcome)
              const currentNonWelcome = messages.filter(m => m.id !== 'welcome')
              if (loaded.length > currentNonWelcome.length) {
                setMessages([{ ...WELCOME_MESSAGE, id: 'welcome', timestamp: 0 }, ...loaded])
              }
            }
          })
          .catch(() => { /* silent — best effort */ })
        // Also refresh session list
        listSessions().then(setSessions).catch(console.error)
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => document.removeEventListener('visibilitychange', handleVisibilityChange)
  }, [email, currentSessionId, loading, messages])

  const handleSend = useCallback(async (text: string, files?: UploadedFile[]) => {
    // Build file refs for the agent
    const fileRefs = files?.map(f => ({ filename: f.filename, s3_key: f.key })) || []

    let fullMessage = text
    if (files && files.length > 0) {
      const fileList = files.map(f => `[קובץ מצורף: ${f.filename} (s3://${f.key})]`).join('\n')
      fullMessage = fullMessage ? `${fullMessage}\n\n${fileList}` : fileList
    }

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: fullMessage,
      timestamp: Date.now(),
    }
    setMessages(prev => [...prev, userMsg])
    setLoading(true)
    setStreamingContent('')

    // Create abort controller for this request
    const controller = new AbortController()
    abortControllerRef.current = controller

    const streamingMsgId = crypto.randomUUID()

    await streamChat({
      email,
      message: fullMessage,
      sessionId: currentSessionId,
      fileRefs,
      signal: controller.signal,
      onChunk: (chunk) => {
        // Strip keepalive markers before processing
        const cleaned = chunk.replace(/__KEEPALIVE__/g, '')
        if (!cleaned) return  // Pure keepalive chunk — skip

        // Raw chunk from ReadableStream — accumulate for SSE parsing
        setStreamingContent(prev => prev + cleaned)

        // Scan for progress events in the new chunk
        // Progress events now come as: __PROGRESS__{"type":"progress",...}
        const prefixMatch = cleaned.match(/__PROGRESS__.*?"label":\s*"([^"]+)"/)
        if (prefixMatch) {
          setProgressLabel(prefixMatch[1])
        } else {
          // Fallback: legacy format without prefix
          const progressMatch = cleaned.match(/"type":\s*"progress".*?"label":\s*"([^"]+)"/)
          if (progressMatch) {
            setProgressLabel(progressMatch[1])
          }
        }
      },
      onDone: (fullText) => {
        // Parse the SSE data format — extract text from "data: ..." lines
        const parsedText = parseStreamData(fullText)

        const assistantMsg: Message = {
          id: streamingMsgId,
          role: 'assistant',
          content: parsedText,
          timestamp: Date.now(),
        }
        setMessages(prev => [...prev, assistantMsg])
        setLoading(false)
        setStreamingContent('')
        setProgressLabel('')
        abortControllerRef.current = null
        // Refresh sessions (immediate + delayed to catch name_session updates)
        listSessions().then(setSessions).catch(console.error)
        setTimeout(() => listSessions().then(setSessions).catch(console.error), 2000)
        // Check for completed long-running jobs after every agent response
        checkNowRef.current()
      },
      onError: async (err) => {
        abortControllerRef.current = null

        // Show partial content if we have any
        const partialText = streamingContent ? parseStreamData(streamingContent).trim() : ''
        if (partialText) {
          setMessages(prev => [...prev, {
            id: crypto.randomUUID(),
            role: 'assistant' as const,
            content: partialText,
            timestamp: Date.now(),
          }])
        }

        // Retry fetching the full response from server (it may have been saved)
        const MAX_RETRIES = 5
        for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
          const delay = Math.min(1000 * Math.pow(2, attempt - 1), 16000) // 1s, 2s, 4s, 8s, 16s
          setProgressLabel(`⏳ בודק תשובה מהשרת... (${attempt}/${MAX_RETRIES})`)
          setStreamingContent('') // clear streaming so progress shows via loading

          await new Promise(r => setTimeout(r, delay))

          try {
            const { messages: serverMsgs } = await getSessionMessages(currentSessionId)
            // Check if server has an assistant message newer than our last user message
            const currentNonWelcome = messages.filter(m => m.id !== 'welcome')
            if (serverMsgs.length > currentNonWelcome.length) {
              const loaded: Message[] = serverMsgs.map((m: any, i: number) => ({
                id: `recovered-${i}`,
                role: m.role as 'user' | 'assistant',
                content: m.content,
                timestamp: new Date(m.timestamp).getTime(),
              }))
              setMessages([{ ...WELCOME_MESSAGE, id: 'welcome', timestamp: 0 }, ...loaded])
              setLoading(false)
              setStreamingContent('')
              setProgressLabel('')
              listSessions().then(setSessions).catch(console.error)
              return // Success — recovered the response
            }
          } catch {
            // Server unreachable — continue retrying
          }
        }

        // All retries exhausted — show error
        if (!partialText) {
          setMessages(prev => [...prev, {
            id: crypto.randomUUID(),
            role: 'assistant' as const,
            content: `⚠️ שגיאה: ${err.message}`,
            timestamp: Date.now(),
          }])
        }
        setLoading(false)
        setStreamingContent('')
        setProgressLabel('')
      },
    })
  }, [email, currentSessionId])

  // ── Job polling ────────────────────────────────────────────────────────────
  const handleJobsReady = useCallback(() => {
    // Don't interrupt an in-flight request; jobs stay unconsumed so next 60s tick will retry.
    if (loading) return
    handleSendRef.current('יש עבודות שהסתיימו, בדוק בבקשה')
  }, [loading])

  const { hasPending, checkNow } = useJobPolling({
    sessionId: currentSessionId,
    enabled: true,
    onJobsReady: handleJobsReady,
  })

  // Keep refs current to break circular dependencies
  useEffect(() => { checkNowRef.current = checkNow }, [checkNow])
  useEffect(() => { handleSendRef.current = handleSend }, [handleSend])

  const handleNewChat = useCallback(() => {
    // Abort any in-flight stream
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setLoading(false)
    setStreamingContent('')
    setProgressLabel('')
    setMessages([{ ...WELCOME_MESSAGE, id: crypto.randomUUID(), timestamp: Date.now() }])
    setCurrentSessionId(crypto.randomUUID())
    setSessionFiles([])
    setSharedWith([])
    setIsSharedSession(false)
    setShowFiles(false)
    setAccess('owner')
    setVisibility('private')
    updateUrl(null)
  }, [updateUrl])

  const handleSelectSession = useCallback(async (sessionId: string) => {
    abortControllerRef.current?.abort()
    abortControllerRef.current = null
    setLoading(false)
    setStreamingContent('')
    setProgressLabel('')
    setCurrentSessionId(sessionId)
    setShowFiles(false)
    updateUrl(sessionId)
    try {
      const data = await getSessionMessages(sessionId)
      setMessages(data.messages.map(m => ({
        id: `${m.timestamp}-${m.role}`,
        role: m.role,
        content: m.content,
        timestamp: new Date(m.timestamp).getTime(),
      })))
      setSessionFiles(data.files)
      setSharedWith(data.shared_with)
      if (data.access) setAccess(data.access)
      if (data.visibility) setVisibility(data.visibility)
      const session = sessions.find(s => s.session_id === sessionId)
      setIsSharedSession(session?._shared || false)
    } catch (err) {
      console.error('Failed to load session:', err)
    }
  }, [email, sessions, updateUrl])

  // Keep popstate refs current
  useEffect(() => { handleNewChatRef.current = handleNewChat }, [handleNewChat])
  useEffect(() => { handleSelectSessionRef.current = handleSelectSession }, [handleSelectSession])

  const handleUpload = useCallback(async (file: File): Promise<UploadedFile | null> => {
    try {
      const result = await uploadFile(currentSessionId, file)
      setSessionFiles(prev => [...prev, {
        file_id: result.file_id,
        filename: result.filename,
        s3_key: result.key,
        content_type: file.type,
        uploaded_at: new Date().toISOString(),
      }])
      return { key: result.key, filename: result.filename, file_id: result.file_id }
    } catch (err) {
      console.error('Upload failed:', err)
      return null
    }
  }, [email, currentSessionId])

  const handleTranscribe = useCallback(async (audioBlob: Blob): Promise<string> => {
    try {
      const result = await transcribeAudio(audioBlob, currentSessionId)
      return result.text || ''
    } catch (err: any) {
      console.error('Transcription failed:', err)
      const errorMsg = err?.message?.includes('timed out')
        ? 'התמלול נכשל — נסה הודעה קצרה יותר'
        : `שגיאה בתמלול: ${err?.message || 'unknown'}`
      alert(errorMsg)
      return ''
    }
  }, [email, currentSessionId])

  const handleDeleteSession = useCallback(async (sessionId: string) => {
    try {
      await deleteSession(sessionId)
      setSessions(prev => prev.filter(s => s.session_id !== sessionId))
      // If we deleted the current session, start fresh
      if (sessionId === currentSessionId) {
        handleNewChat()
      }
    } catch (err) {
      console.error('Delete failed:', err)
      // Refresh sessions to restore the list
      listSessions().then(setSessions).catch(console.error)
    }
  }, [email, currentSessionId, handleNewChat])

  const handleShare = useCallback(async (shareWithEmail: string) => {
    try {
      await shareSession(currentSessionId, shareWithEmail)
      setSharedWith(prev => [...prev, shareWithEmail])
      setShowShareModal(false)
    } catch (err) {
      console.error('Share failed:', err)
      throw err
    }
  }, [email, currentSessionId])

  const handleVisibilityChange = useCallback(async (newVisibility: 'private' | 'public') => {
    try {
      await setSessionVisibility(currentSessionId, newVisibility)
      setVisibility(newVisibility)
    } catch (err) {
      console.error('Visibility change failed:', err)
      throw err
    }
  }, [currentSessionId])

  const handleUnshare = useCallback(async (emailToRemove: string) => {
    try {
      await unshareSession(currentSessionId, emailToRemove)
      setSharedWith(prev => prev.filter(e => e !== emailToRemove))
    } catch (err) {
      console.error('Unshare failed:', err)
      throw err
    }
  }, [currentSessionId])

  const handleFileDownload = useCallback(async (fileId: string) => {
    try {
      const url = await getFileDownloadUrl(currentSessionId, fileId)
      window.open(url, '_blank')
    } catch (err) {
      console.error('Download failed:', err)
    }
  }, [currentSessionId, email])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortControllerRef.current?.abort()
    }
  }, [])

  // Compute display messages — include streaming content as a live message
  const displayMessages = streamingContent
    ? [...messages, {
        id: 'streaming',
        role: 'assistant' as const,
        content: parseStreamData(streamingContent),
        timestamp: Date.now(),
      }]
    : messages

  return (
    <div className="flex h-screen bg-gray-950" dir="rtl">
      <Sidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelect={handleSelectSession}
        onNewChat={handleNewChat}
        onDelete={handleDeleteSession}
        email={email}
        onLogout={onLogout}
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main chat area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Header */}
        <div className="border-b border-gray-800 px-4 lg:px-6 py-4 flex items-center gap-3">
          <button
            onClick={() => setSidebarOpen(true)}
            className="lg:hidden p-1.5 rounded-lg hover:bg-gray-800 text-gray-400 transition-colors"
            title="תפריט"
          >
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" className="w-5 h-5">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          </button>
          <span className="text-2xl">🎬</span>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <h1 className="font-semibold text-white">StoryTeller</h1>
              {hasPending && (
                <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-400 text-xs animate-pulse">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  מעבד...
                </span>
              )}
              {(isSharedSession || sharedWith.length > 0) && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-brand-900/50 text-brand-300 text-xs">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-3 h-3">
                    <path d="M15 19.128a9.38 9.38 0 002.625.372 9.337 9.337 0 004.121-.952 4.125 4.125 0 00-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 018.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0111.964-3.07M12 6.375a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0zm8.25 2.25a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
                  </svg>
                  משותפת
                </span>
              )}
              {access === 'viewer' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-yellow-900/50 text-yellow-300 text-xs">
                  📖 צפייה
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500">עוזר תכנון סרטוני YouTube</p>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-1">
            {sessionFiles.length > 0 && (
              <button
                onClick={() => setShowFiles(!showFiles)}
                className="p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors relative"
                title="קבצים"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
                <span className="absolute -top-1 -left-1 w-4 h-4 bg-brand-600 rounded-full text-[10px] flex items-center justify-center text-white">
                  {sessionFiles.length}
                </span>
              </button>
            )}

            <button
              onClick={() => setShowShareModal(true)}
              className={`p-2 rounded-lg hover:bg-gray-800 text-gray-400 hover:text-gray-200 transition-colors ${access === 'viewer' ? 'hidden' : ''}`}
              title="שתף שיחה"
            >
              <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-5 h-5">
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.217 10.907a2.25 2.25 0 100 2.186m0-2.186c.18.324.283.696.283 1.093s-.103.77-.283 1.093m0-2.186l9.566-5.314m-9.566 7.5l9.566 5.314m0 0a2.25 2.25 0 103.935 2.186 2.25 2.25 0 00-3.935-2.186zm0-12.814a2.25 2.25 0 103.933-2.185 2.25 2.25 0 00-3.933 2.185z" />
              </svg>
            </button>
          </div>
        </div>

        {/* Files panel */}
        {showFiles && sessionFiles.length > 0 && (
          <FileList files={sessionFiles} onDownload={handleFileDownload} />
        )}

        <ChatMessages
          messages={displayMessages}
          loading={loading && !streamingContent}
          loadingText={progressLabel || 'מתחבר לסוכן...'}
          progressLabel={streamingContent ? progressLabel : ''}
          streamingContent={streamingContent}
          isStreaming={loading && !!streamingContent}
          email={email}
          sessionId={currentSessionId}
        />
        {access === 'viewer' ? (
          <div className="border-t border-gray-800 px-4 py-3 text-center text-sm text-yellow-400 bg-gray-900/50">
            📖 שיחה לקריאה בלבד
          </div>
        ) : (
          <ChatInput onSend={handleSend} disabled={loading} onUpload={handleUpload} onTranscribe={handleTranscribe} />
        )}
      </div>

      {showShareModal && access !== 'viewer' && (
        <ShareModal
          onShare={handleShare}
          onClose={() => setShowShareModal(false)}
          sharedWith={sharedWith}
          visibility={visibility}
          onVisibilityChange={handleVisibilityChange}
          onUnshare={handleUnshare}
          sessionId={currentSessionId}
        />
      )}
    </div>
  )
}

/**
 * Parse SSE-style "data: ..." lines from the stream into plain text.
 * Each chunk comes as: data: "quoted text"\n\n
 * The values are JSON-encoded strings.
 */
function parseStreamData(raw: string): string {
  if (!raw.includes('data: ')) return raw

  const lines = raw.split('\n')
  const textParts: string[] = []

  for (const line of lines) {
    if (!line.startsWith('data: ')) continue
    const value = line.slice(6).trim()
    if (!value) continue

    try {
      const parsed = JSON.parse(value)
      if (typeof parsed === 'string') {
        // Check if it's a progress event (prefixed or raw JSON)
        if (parsed.startsWith('__PROGRESS__')) continue
        if (parsed === '__KEEPALIVE__') continue
        // Also catch legacy un-prefixed progress JSON that got string-wrapped
        if (parsed.includes('"type"') && parsed.includes('"progress"')) {
          try {
            const inner = JSON.parse(parsed)
            if (inner && inner.type === 'progress') continue
          } catch { /* not JSON, keep as text */ }
        }
        textParts.push(parsed)
      }
      // JSON objects (progress events, etc.) — skip silently
    } catch {
      // Not valid JSON — use raw as fallback
      textParts.push(value)
    }
  }

  return textParts.join('')
}
