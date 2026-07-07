/**
 * InteractiveChoices — renders option chips (single or multi select).
 * Supports an optional free-text input that gets appended to the selection.
 */
import { useState } from 'react'
import type { InteractiveChoices as ChoicesType } from './types'

interface Props {
  block: ChoicesType
  onSelect: (selectedIds: string[], freeText?: string) => void
  disabled?: boolean
  /** Pre-selected IDs (for history rendering) */
  selectedIds?: string[]
  /** When true, single-select doesn't auto-send (multi-block form mode) */
  deferSend?: boolean
}

export default function InteractiveChoices({ block, onSelect, disabled, selectedIds: initialSelected, deferSend }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set(initialSelected || []))
  const [freeText, setFreeText] = useState('')
  const [showFreeText, setShowFreeText] = useState(false)
  const isResponded = disabled || (!deferSend && initialSelected && initialSelected.length > 0)

  const handleClick = (id: string, option: { freeText?: boolean }) => {
    if (isResponded) return

    if (option.freeText) {
      // Toggle free text input
      setShowFreeText(!showFreeText)
      return
    }

    if (block.mode === 'single') {
      setSelected(new Set([id]))
      if (!deferSend) {
        // Immediate send only when NOT in form mode
        onSelect([id], freeText.trim() || undefined)
      } else {
        // In form mode, just notify parent of selection (no send)
        onSelect([id], undefined)
      }
    } else {
      // Multi select — toggle
      const next = new Set(selected)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      setSelected(next)
      if (deferSend) {
        onSelect([...next], undefined)
      }
    }
  }

  const handleConfirm = () => {
    if (selected.size === 0 && !freeText.trim()) return
    if (isResponded) return
    onSelect([...selected], freeText.trim() || undefined)
  }

  const handleFreeTextSubmit = () => {
    if (!freeText.trim() || isResponded) return
    onSelect([], freeText.trim())
  }

  return (
    <div className="mt-3 space-y-2">
      <div className="flex flex-wrap gap-2" dir="rtl">
        {block.options.map(option => {
          const isSelected = selected.has(option.id)
          const isFreeTextOption = option.freeText
          return (
            <button
              key={option.id}
              onClick={() => handleClick(option.id, option)}
              disabled={!!isResponded}
              className={`
                px-4 py-2 rounded-xl text-sm font-medium transition-all duration-150
                border
                ${isSelected
                  ? 'bg-brand-600 border-brand-500 text-white shadow-md'
                  : isFreeTextOption && showFreeText
                    ? 'bg-brand-900/50 border-brand-600 text-brand-300'
                    : isResponded
                      ? 'bg-gray-800/50 border-gray-700 text-gray-500 cursor-default'
                      : 'bg-gray-800 border-gray-700 text-gray-200 hover:border-brand-500 hover:bg-gray-750 cursor-pointer'
                }
                ${isResponded && !isSelected ? 'opacity-50' : ''}
              `}
              title={option.description}
            >
              <span className="ml-1.5 text-brand-400 font-bold">{option.id}</span>
              {option.label}
            </button>
          )
        })}
      </div>

      {/* Free text input area */}
      {showFreeText && !isResponded && (
        <div className="flex gap-2" dir="rtl">
          <input
            type="text"
            value={freeText}
            onChange={e => setFreeText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && freeText.trim()) {
                e.preventDefault()
                handleFreeTextSubmit()
              }
            }}
            placeholder="כתוב תשובה חופשית..."
            className="flex-1 px-4 py-2 rounded-xl bg-gray-800 border border-gray-700 text-white text-sm placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-brand-500"
            autoFocus
          />
          <button
            onClick={handleFreeTextSubmit}
            disabled={!freeText.trim()}
            className={`
              px-4 py-2 rounded-xl text-sm font-medium transition-all
              ${freeText.trim()
                ? 'bg-brand-600 hover:bg-brand-500 text-white'
                : 'bg-gray-800 text-gray-500 cursor-not-allowed'
              }
            `}
          >
            שלח
          </button>
        </div>
      )}

      {/* Multi-select confirm button */}
      {block.mode === 'multi' && !isResponded && !showFreeText && (
        <button
          onClick={handleConfirm}
          disabled={selected.size === 0}
          className={`
            mt-2 px-5 py-2 rounded-xl text-sm font-medium transition-all
            ${selected.size > 0
              ? 'bg-brand-600 hover:bg-brand-500 text-white'
              : 'bg-gray-800 text-gray-500 cursor-not-allowed'
            }
          `}
        >
          {block.confirmLabel || `שלח (${selected.size})`}
        </button>
      )}
    </div>
  )
}
