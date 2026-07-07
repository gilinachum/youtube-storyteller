/**
 * Interactive block parser and types for agent-generated UI elements.
 *
 * The agent embeds structured JSON in HTML comments:
 *   <!-- ui:interactive { ... } -->
 *
 * The frontend parses these and renders them as interactive components.
 */

export interface ChoiceOption {
  id: string
  label: string
  description?: string
  freeText?: boolean
}

export interface GridItem {
  id: string
  title: string
  thumbnail?: string
  subtitle?: string
  url?: string
}

export interface InteractiveChoices {
  type: 'choices'
  id: string
  mode: 'single' | 'multi'
  prompt?: string
  options: ChoiceOption[]
  confirmLabel?: string
}

export interface InteractiveGrid {
  type: 'grid'
  id: string
  mode: 'single' | 'multi'
  prompt?: string
  columns?: number
  items: GridItem[]
  confirmLabel?: string
}

export interface InteractiveConfirm {
  type: 'confirm'
  id: string
  prompt?: string
  yesLabel?: string
  noLabel?: string
}

export type InteractiveBlock = InteractiveChoices | InteractiveGrid | InteractiveConfirm

export interface ParsedMessage {
  /** The message content with interactive blocks removed */
  textContent: string
  /** Any interactive blocks found */
  blocks: InteractiveBlock[]
}

const INTERACTIVE_REGEX = /<!--\s*ui:interactive\s*([\s\S]*?)-->/g

/**
 * Parse a message string and extract interactive blocks.
 * Returns the cleaned text and any interactive blocks found.
 */
export function parseInteractiveBlocks(content: string): ParsedMessage {
  const blocks: InteractiveBlock[] = []
  let textContent = content

  const matches = [...content.matchAll(INTERACTIVE_REGEX)]
  for (const match of matches) {
    try {
      const jsonStr = match[1].trim()
      const parsed = JSON.parse(jsonStr)
      if (parsed && parsed.type && parsed.id) {
        // Validate required arrays exist for each type
        if (parsed.type === 'choices' && !Array.isArray(parsed.options)) continue
        if (parsed.type === 'grid' && !Array.isArray(parsed.items)) continue
        blocks.push(parsed as InteractiveBlock)
      }
    } catch {
      // If JSON parsing fails, leave the comment in place
      continue
    }
    // Remove the matched comment from text
    textContent = textContent.replace(match[0], '')
  }

  // Clean up extra whitespace left behind
  textContent = textContent.replace(/\n{3,}/g, '\n\n').trim()

  return { textContent, blocks }
}

/**
 * Format a user's selection as a message to send back to the agent.
 */
export function formatSelection(block: InteractiveBlock, selectedIds: string[], freeText?: string): string {
  // If only free text provided (no selections)
  if (selectedIds.length === 0 && freeText) {
    return freeText
  }

  if (block.type === 'confirm') {
    return selectedIds[0] === 'yes' ? 'כן' : 'לא'
  }

  if (block.type === 'choices') {
    const selected = block.options.filter(o => selectedIds.includes(o.id))
    let message: string
    if (selected.length === 1) {
      message = `${selected[0].id}. ${selected[0].label}`
    } else if (selected.length > 1) {
      message = selected.map(o => `${o.id}. ${o.label}`).join(', ')
    } else {
      message = ''
    }
    // Append free text if provided
    if (freeText) {
      message = message ? `${message}\n${freeText}` : freeText
    }
    return message || ''
  }

  if (block.type === 'grid') {
    const selected = block.items.filter(item => selectedIds.includes(item.id))
    if (selected.length === 0) return 'לא בחרתי כלום'
    const titles = selected.map(item => `• ${item.title}`)
    return `בחרתי ${selected.length} סרטונים לניתוח:\n${titles.join('\n')}`
  }

  return selectedIds.join(', ')
}

/**
 * Check if a message has already been responded to (for history rendering).
 * We look at the next user message after this assistant message.
 */
export function isBlockResponded(_blockId: string, _messageIndex: number, _messages: { role: string; content: string }[]): boolean {
  // Simple heuristic: if there's a user message after this one, the block was responded to
  // The actual selection state would need to be stored, but for now we grey out
  // blocks that appear before the last assistant message
  return false // Let the component handle this via props
}
