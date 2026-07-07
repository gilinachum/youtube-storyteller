/**
 * InteractiveGrid — renders a grid of cards with thumbnails (e.g., YouTube videos).
 * Supports single and multi select.
 */
import { useState } from 'react'
import type { InteractiveGrid as GridType } from './types'

interface Props {
  block: GridType
  onSelect: (selectedIds: string[]) => void
  disabled?: boolean
  selectedIds?: string[]
}

export default function InteractiveGrid({ block, onSelect, disabled, selectedIds: initialSelected }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set(initialSelected || []))
  const isResponded = disabled || (initialSelected && initialSelected.length > 0)

  const handleClick = (id: string) => {
    if (isResponded) return

    if (block.mode === 'single') {
      setSelected(new Set([id]))
      onSelect([id])
    } else {
      const next = new Set(selected)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      setSelected(next)
    }
  }

  const handleConfirm = () => {
    if (selected.size === 0 || isResponded) return
    onSelect([...selected])
  }

  const columns = Math.min(block.columns || 4, 6)

  return (
    <div className="mt-3 space-y-3" dir="rtl">
      <div
        className="grid gap-2"
        style={{ gridTemplateColumns: `repeat(${columns}, 1fr)` }}
      >
        {block.items.map(item => {
          const isSelected = selected.has(item.id)
          // Only allow https thumbnails
          const safeThumbnail = item.thumbnail && item.thumbnail.startsWith('https://') ? item.thumbnail : undefined
          return (
            <button
              key={item.id}
              onClick={() => handleClick(item.id)}
              disabled={!!isResponded}
              className={`
                relative rounded-xl overflow-hidden border-2 transition-all duration-150
                text-right
                ${isSelected
                  ? 'border-brand-500 ring-2 ring-brand-500/30 shadow-lg'
                  : isResponded
                    ? 'border-gray-800 opacity-50 cursor-default'
                    : 'border-gray-800 hover:border-gray-600 cursor-pointer'
                }
              `}
            >
              {/* Thumbnail */}
              {safeThumbnail && (
                <div className="aspect-video w-full overflow-hidden bg-gray-900">
                  <img
                    src={safeThumbnail}
                    alt={item.title}
                    className="w-full h-full object-cover"
                    loading="lazy"
                  />
                </div>
              )}

              {/* Content */}
              <div className="p-2.5 bg-gray-900">
                <p className="text-xs font-medium text-white/90 line-clamp-2 leading-snug">
                  {item.title}
                </p>
                {item.subtitle && (
                  <p className="text-[10px] text-gray-400 mt-1">{item.subtitle}</p>
                )}
              </div>

              {/* Selection indicator */}
              {isSelected && (
                <div className="absolute top-2 left-2 w-6 h-6 bg-brand-500 rounded-full flex items-center justify-center shadow-md">
                  <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4 text-white">
                    <path fillRule="evenodd" d="M19.916 4.626a.75.75 0 01.208 1.04l-9 13.5a.75.75 0 01-1.154.114l-6-6a.75.75 0 011.06-1.06l5.353 5.353 8.493-12.739a.75.75 0 011.04-.208z" clipRule="evenodd" />
                  </svg>
                </div>
              )}

              {/* Hover overlay for unselected */}
              {!isResponded && !isSelected && (
                <div className="absolute inset-0 bg-brand-500/0 hover:bg-brand-500/10 transition-colors" />
              )}
            </button>
          )
        })}
      </div>

      {/* Multi-select confirm button */}
      {block.mode === 'multi' && !isResponded && (
        <div className="flex items-center gap-3">
          <button
            onClick={handleConfirm}
            disabled={selected.size === 0}
            className={`
              px-5 py-2.5 rounded-xl text-sm font-medium transition-all
              ${selected.size > 0
                ? 'bg-brand-600 hover:bg-brand-500 text-white shadow-md'
                : 'bg-gray-800 text-gray-500 cursor-not-allowed'
              }
            `}
          >
            {block.confirmLabel || `נתח סרטונים נבחרים (${selected.size})`}
          </button>
          {selected.size > 0 && (
            <span className="text-xs text-gray-400">
              {selected.size} נבחרו
            </span>
          )}
        </div>
      )}
    </div>
  )
}
