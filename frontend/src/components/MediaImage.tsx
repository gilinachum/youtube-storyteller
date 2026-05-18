import { useState, useEffect, useRef } from 'react'
import { getFileDownloadUrl } from '../api'

interface Props {
  fileId: string
  alt: string
  sessionId: string
}

/**
 * Renders an inline image from a media:// reference.
 * Fetches a fresh presigned URL on mount and displays with overlay controls.
 */
export default function MediaImage({ fileId, alt, sessionId }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState(false)
  const [hover, setHover] = useState(false)
  const attempted = useRef(false)

  useEffect(() => {
    if (attempted.current) return
    attempted.current = true
    ;(async () => {
      try {
        const downloadUrl = await getFileDownloadUrl(sessionId, fileId)
        setUrl(downloadUrl)
      } catch {
        setError(true)
      }
    })()
  }, [fileId, sessionId])

  if (error) {
    return (
      <div className="my-3 flex items-center gap-2 bg-red-900/30 border border-red-700/50 rounded-lg px-4 py-3 text-sm text-red-300">
        <span>⚠️</span>
        <span>Failed to load image</span>
      </div>
    )
  }

  if (!url) {
    return (
      <div className="my-3 w-48 h-48 rounded-lg bg-gray-700 animate-pulse flex items-center justify-center">
        <svg className="w-6 h-6 text-gray-500 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      </div>
    )
  }

  return (
    <div
      className="my-3 relative inline-block"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <img
        src={url}
        alt={alt || 'image'}
        className="rounded-lg max-w-full border border-gray-700 shadow-lg"
        style={{ maxHeight: '400px', objectFit: 'contain' }}
        loading="lazy"
      />
      {/* Overlay action buttons */}
      {hover && (
        <div className="absolute top-2 left-2 flex gap-1.5">
          <a
            href={url}
            download
            className="bg-gray-900/80 hover:bg-gray-800 text-white rounded-md p-1.5 text-xs backdrop-blur-sm transition-colors"
            title="Download"
          >
            ⬇
          </a>
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="bg-gray-900/80 hover:bg-gray-800 text-white rounded-md p-1.5 text-xs backdrop-blur-sm transition-colors"
            title="Open in new tab"
          >
            ↗
          </a>
        </div>
      )}
      {alt && alt !== 'image' && (
        <p className="text-xs text-gray-400 mt-1">{alt}</p>
      )}
    </div>
  )
}
