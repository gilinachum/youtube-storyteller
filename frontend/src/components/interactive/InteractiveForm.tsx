/**
 * InteractiveForm - wraps multiple interactive blocks as a single form.
 * When there's only one block, it behaves as before (single-select auto-sends).
 * When there are multiple blocks, selections are collected and a single "שלח" button sends them all.
 */
import { useState, useCallback } from 'react'
import InteractiveBlock from './InteractiveBlock'
import { formatSelection } from './types'
import type { InteractiveBlock as BlockType } from './types'

interface Props {
  blocks: BlockType[]
  disabled: boolean
  respondedBlocks: Set<string>
  onSubmit: (message: string) => void
  /** Called when selections change - parent can enable send button */
  onPendingChange?: (pending: string | null) => void
}

export default function InteractiveForm({ blocks, disabled, respondedBlocks, onSubmit, onPendingChange }: Props) {
  const isMultiBlock = blocks.length > 1
  // Track selections per block: { blockId: string[] }
  const [selections, setSelections] = useState<Record<string, string[]>>({})
  const [freeTexts, setFreeTexts] = useState<Record<string, string>>({})

  // Build the combined answer string from current selections
  const buildAnswer = (sels: Record<string, string[]>, texts: Record<string, string>) => {
    const parts: string[] = []
    for (const block of blocks) {
      const selected = sels[block.id]
      const ft = texts[block.id]
      if (selected && selected.length > 0) {
        parts.push(formatSelection(block, selected, ft))
      } else if (ft) {
        parts.push(ft)
      }
    }
    return parts.length > 0 ? parts.join('\n') : null
  }

  const handleSelect = useCallback((blockId: string, selectedIds: string[], freeText?: string) => {
    if (!isMultiBlock) {
      // Single block - send immediately (original behavior)
      const block = blocks.find(b => b.id === blockId)
      if (block) {
        const message = formatSelection(block, selectedIds, freeText)
        if (message) onSubmit(message)
      }
      return
    }

    // Multi-block form mode — just collect the selection
    const newSels = { ...selections, [blockId]: selectedIds }
    setSelections(prev => ({ ...prev, [blockId]: selectedIds }))
    const newTexts = freeText ? { ...freeTexts, [blockId]: freeText } : freeTexts
    if (freeText) {
      setFreeTexts(prev => ({ ...prev, [blockId]: freeText }))
    }
    // Notify parent of pending answer
    if (onPendingChange) {
      onPendingChange(buildAnswer(newSels, newTexts))
    }
  }, [blocks, isMultiBlock, onSubmit, selections, freeTexts, onPendingChange])

  const allResponded = blocks.every(b => respondedBlocks.has(b.id))

  return (
    <div className="space-y-1">
      {blocks.map(block => (
        <InteractiveBlock
          key={block.id}
          block={block}
          disabled={disabled || allResponded || respondedBlocks.has(block.id)}
          onSelect={handleSelect}
          deferSend={isMultiBlock}
          selectedIds={selections[block.id]}
        />
      ))}
    </div>
  )
}
