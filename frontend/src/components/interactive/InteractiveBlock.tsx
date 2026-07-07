/**
 * InteractiveBlock — dispatcher component that renders the correct
 * interactive element based on block type.
 */
import type { InteractiveBlock as BlockType } from './types'
import InteractiveChoices from './InteractiveChoices'
import InteractiveGrid from './InteractiveGrid'
import InteractiveConfirm from './InteractiveConfirm'

interface Props {
  block: BlockType
  onSelect: (blockId: string, selectedIds: string[], freeText?: string) => void
  disabled?: boolean
  selectedIds?: string[]
  /** When true, single-select doesn't auto-send (used in multi-block forms) */
  deferSend?: boolean
}

export default function InteractiveBlock({ block, onSelect, disabled, selectedIds, deferSend }: Props) {
  const handleSelect = (ids: string[], freeText?: string) => {
    onSelect(block.id, ids, freeText)
  }

  switch (block.type) {
    case 'choices':
      return (
        <InteractiveChoices
          block={block}
          onSelect={handleSelect}
          disabled={disabled}
          selectedIds={selectedIds}
          deferSend={deferSend}
        />
      )
    case 'grid':
      return (
        <InteractiveGrid
          block={block}
          onSelect={handleSelect}
          disabled={disabled}
          selectedIds={selectedIds}
        />
      )
    case 'confirm':
      return (
        <InteractiveConfirm
          block={block}
          onSelect={handleSelect}
          disabled={disabled}
          selectedIds={selectedIds}
        />
      )
    default:
      return null
  }
}
