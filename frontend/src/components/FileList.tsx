import type { FileRecord } from '../api'

interface Props {
  files: FileRecord[]
  onDownload: (fileId: string) => void
}

const FILE_ICONS: Record<string, string> = {
  'application/pdf': '📕',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation': '📊',
  'application/vnd.ms-powerpoint': '📊',
  'text/plain': '📄',
  'text/markdown': '📝',
  'application/msword': '📄',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '📄',
}

export default function FileList({ files, onDownload }: Props) {
  return (
    <div className="border-b border-gray-800 bg-gray-900/50 px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-4 h-4 text-gray-400">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
        <span className="text-xs text-gray-400 font-medium">קבצים בשיחה ({files.length})</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {files.map(f => (
          <button
            key={f.file_id}
            onClick={() => onDownload(f.file_id)}
            className="flex items-center gap-2 px-3 py-2 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-xl text-sm text-gray-300 hover:text-white transition-colors group"
            title={`הורד: ${f.filename}`}
          >
            <span>{FILE_ICONS[f.content_type] || '📎'}</span>
            <span className="truncate max-w-[140px]">{f.filename}</span>
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor" className="w-3.5 h-3.5 text-gray-500 group-hover:text-brand-400 transition-colors">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
          </button>
        ))}
      </div>
    </div>
  )
}
