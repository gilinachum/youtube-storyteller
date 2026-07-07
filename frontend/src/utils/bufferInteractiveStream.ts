/**
 * bufferInteractiveStream — strips incomplete <!-- ui:interactive ... --> blocks
 * from streaming display so the user never sees raw markup mid-stream.
 *
 * Returns the safe-to-display portion of the text.
 */
export function bufferInteractiveStream(text: string): string {
  if (!text) return ''

  // Find the last opening tag for an interactive block
  const openTag = text.lastIndexOf('<!-- ui:interactive')
  if (openTag === -1) return text

  // Check if it's been closed
  const closeTag = text.indexOf('-->', openTag)
  if (closeTag === -1) {
    // Incomplete block — show only content before it
    return text.slice(0, openTag).trim()
  }

  // Closed — safe to show everything
  return text
}
