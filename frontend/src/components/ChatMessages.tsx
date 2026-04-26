import { useEffect, useRef, useCallback } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getFileDownloadUrl } from '../api'

const FILE_ICON_MAP: Record<string, string> = {
  pdf: '📕',
  pptx: '📊',
  ppt: '📊',
  doc: '📄',
  docx: '📄',
  txt: '📄',
  md: '📄',
}

function getFileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || ''
  return FILE_ICON_MAP[ext] || '📁'
}

/** Parse user message content — render file attachment refs as styled cards */
function UserMessage({ content, email }: { content: string; email?: string }) {
  // Match [קובץ מצורף: filename (s3_key)] or 📎 filename patterns
  const fileRefRegex = /\[קובץ מצורף: (.+?) \((?:s3:\/\/)?(.+?)\)\]/g
  const clipRegex = /\n?📎 .+/g

  // Extract file refs
  const files: { filename: string; key: string }[] = []
  let match
  while ((match = fileRefRegex.exec(content)) !== null) {
    files.push({ filename: match[1], key: match[2] })
  }

  // Get the clean text (remove file ref lines and 📎 lines)
  let cleanText = content
    .replace(fileRefRegex, '')
    .replace(clipRegex, '')
    .trim()

  return (
    <div>
      {cleanText && <p>{cleanText}</p>}
      {files.length > 0 && (
        <div className={`flex flex-col gap-1.5 ${cleanText ? 'mt-2' : ''}`}>
          {files.map((f, i) => (
            <a
              key={i}
              href="#"
              onClick={async (e) => {
                e.preventDefault()
                try {
                  // Extract session_id and file_id from s3 key: uploads/email/session_id/file_id-filename
                  const parts = f.key.replace(/^s3:\/\/[^/]+\//, '').split('/')
                  const sessionId = parts.length >= 3 ? parts[2] : ''
                  const fileIdMatch = parts[parts.length - 1]?.match(/^([a-f0-9-]+?)-/)
                  const fileId = fileIdMatch ? fileIdMatch[1] : ''
                  if (sessionId && fileId) {
                    const url = await getFileDownloadUrl(sessionId, fileId, email || '')
                    window.open(url, '_blank')
                  }
                } catch {
                  // Fallback: can't download
                }
              }}
              className="flex items-center gap-2 bg-white/10 hover:bg-white/15 transition-colors rounded-lg px-3 py-2 text-sm cursor-pointer"
            >
              <span className="text-base">{getFileIcon(f.filename)}</span>
              <span className="truncate max-w-[200px] text-white/90">{f.filename}</span>
              <span className="text-white/50 mr-auto text-xs">⬇</span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

/** Custom markdown renderers — turns S3 presigned download links into file cards */
const markdownComponents: Components = {
  a({ href, children }) {
    // Detect S3 presigned download links
    if (href && (href.includes('.s3.') || href.includes('s3.amazonaws.com')) && href.includes('X-Amz-Signature')) {
      // Extract filename from URL path
      const urlPath = new URL(href).pathname
      const filename = decodeURIComponent(urlPath.split('/').pop() || 'document')
        .replace(/^[a-f0-9]{8}-/, '') // strip file_id prefix
      const ext = filename.split('.').pop()?.toLowerCase() || ''
      const icon = FILE_ICON_MAP[ext] || '\ud83d\udcc1'

      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center gap-2 bg-white/10 hover:bg-white/15 transition-colors rounded-lg px-3 py-2 text-sm no-underline my-2 max-w-[280px]"
        >
          <span className="text-xl flex-shrink-0">{icon}</span>
          <span className="truncate text-white/90">{filename}</span>
          <span className="text-white/50 mr-auto text-xs">\u2b07</span>
        </a>
      )
    }

    // Regular links
    return (
      <a href={href} target="_blank" rel="noopener noreferrer" className="text-brand-400 underline">
        {children}
      </a>
    )
  },
  // Render tables with horizontal scroll and styling
  table({ children }) {
    return (
      <div className="overflow-x-auto my-3 rounded-lg border border-gray-700">
        <table className="min-w-full text-sm border-collapse">{children}</table>
      </div>
    )
  },
  th({ children }) {
    return <th className="bg-gray-800 px-3 py-2 text-right font-medium text-gray-300 border-b border-gray-700">{children}</th>
  },
  td({ children }) {
    return <td className="px-3 py-2 text-right border-b border-gray-800">{children}</td>
  },
  // Render thumbnail/inline images with proper styling
  img({ src, alt }) {
    return (
      <div className="my-3">
        <img
          src={src}
          alt={alt || 'thumbnail'}
          className="rounded-lg max-w-full border border-gray-700 shadow-lg"
          style={{ maxHeight: '400px', objectFit: 'contain' }}
          loading="lazy"
        />
        {alt && alt !== 'thumbnail' && (
          <p className="text-xs text-gray-400 mt-1">{alt}</p>
        )}
      </div>
    )
  },
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  timestamp: number
}

interface Props {
  messages: Message[]
  loading: boolean
  loadingText?: string
  progressLabel?: string
  streamingContent?: string
  email?: string
}

export default function ChatMessages({ messages, loading, loadingText, progressLabel, streamingContent, email }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const isStickRef = useRef(true)

  // Track if user is near the bottom (within 150px)
  const handleScroll = useCallback(() => {
    const el = containerRef.current
    if (!el) return
    const threshold = 150
    isStickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < threshold
  }, [])

  // Auto-scroll only if user hasn't scrolled up
  useEffect(() => {
    if (isStickRef.current) {
      // Use instant scroll during streaming to avoid smooth animation conflicts
      const el = containerRef.current
      if (el) {
        el.scrollTop = el.scrollHeight
      }
    }
  }, [messages, loading, streamingContent])

  // Always scroll to bottom when user sends a new message
  useEffect(() => {
    const lastMsg = messages[messages.length - 1]
    if (lastMsg?.role === 'user') {
      isStickRef.current = true
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages.length])

  return (
    <div ref={containerRef} onScroll={handleScroll} className="flex-1 overflow-y-auto scrollbar-thin px-4 py-6 space-y-4">
      {messages.map(msg => (
        <div
          key={msg.id}
        >
          <div className={`${msg.role === 'user' ? 'message-bubble message-user' : 'message-assistant px-1 py-2 max-w-[90%]'}`}>
            {msg.role === 'user' ? (
              <UserMessage content={msg.content} email={email} />
            ) : (
              <div className="prose-rtl">
                <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{msg.content}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      ))}

      {loading && (
        <div>
          <div className="message-assistant px-1 py-2">
            <div className="flex items-center gap-2 text-gray-400">
              <div className="flex gap-1">
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-brand-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
              <span className="text-sm">{loadingText || 'חוקר ומנתח...'}</span>
            </div>
          </div>
        </div>
      )}

      {/* Progress indicator during streaming */}
      {progressLabel && !loading && (
        <div>
          <div className="bg-gray-800/50 border border-gray-700/50 rounded-xl px-4 py-2 text-gray-400 text-sm flex items-center gap-2">
            <div className="w-2 h-2 bg-brand-400 rounded-full animate-pulse" />
            <span>{progressLabel}</span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  )
}
