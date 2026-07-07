/**
 * InteractiveConfirm — simple Yes/No confirmation buttons.
 */
import { useState } from 'react'
import type { InteractiveConfirm as ConfirmType } from './types'

interface Props {
  block: ConfirmType
  onSelect: (selectedIds: string[]) => void
  disabled?: boolean
  selectedIds?: string[]
}

export default function InteractiveConfirm({ block, onSelect, disabled, selectedIds: initialSelected }: Props) {
  const [selected, setSelected] = useState<string | null>(initialSelected?.[0] || null)
  const isResponded = disabled || (initialSelected && initialSelected.length > 0)

  const handleClick = (value: 'yes' | 'no') => {
    if (isResponded) return
    setSelected(value)
    onSelect([value])
  }

  return (
    <div className="mt-3 flex gap-2" dir="rtl">
      <button
        onClick={() => handleClick('yes')}
        disabled={!!isResponded}
        className={`
          px-5 py-2 rounded-xl text-sm font-medium transition-all border
          ${selected === 'yes'
            ? 'bg-green-600 border-green-500 text-white'
            : isResponded
              ? 'bg-gray-800/50 border-gray-700 text-gray-500 opacity-50'
              : 'bg-gray-800 border-gray-700 text-gray-200 hover:border-green-500 hover:bg-green-900/30'
          }
        `}
      >
        {block.yesLabel || '✓ כן'}
      </button>
      <button
        onClick={() => handleClick('no')}
        disabled={!!isResponded}
        className={`
          px-5 py-2 rounded-xl text-sm font-medium transition-all border
          ${selected === 'no'
            ? 'bg-red-600 border-red-500 text-white'
            : isResponded
              ? 'bg-gray-800/50 border-gray-700 text-gray-500 opacity-50'
              : 'bg-gray-800 border-gray-700 text-gray-200 hover:border-red-500 hover:bg-red-900/30'
          }
        `}
      >
        {block.noLabel || '✗ לא'}
      </button>
    </div>
  )
}
