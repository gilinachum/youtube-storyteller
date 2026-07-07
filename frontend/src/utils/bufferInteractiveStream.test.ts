import { describe, it, expect } from 'vitest'
import { bufferInteractiveStream } from './bufferInteractiveStream'

describe('bufferInteractiveStream', () => {
  it('returns empty string for empty input', () => {
    expect(bufferInteractiveStream('')).toBe('')
  })

  it('returns plain text unchanged', () => {
    const text = 'שלום! מה נושא הסרטון?'
    expect(bufferInteractiveStream(text)).toBe(text)
  })

  it('returns text with completed interactive block unchanged', () => {
    const text = `הנה אופציות:

<!-- ui:interactive
{"type":"choices","id":"q1","mode":"single","options":[{"id":"א","label":"אופציה 1"}]}
-->`
    expect(bufferInteractiveStream(text)).toBe(text)
  })

  it('hides incomplete interactive block mid-stream', () => {
    const text = `הנה אופציות:

<!-- ui:interactive
{"type":"choices","id":"q1","mode":"single","options":[{"id":"א","label":"אופ`
    expect(bufferInteractiveStream(text)).toBe('הנה אופציות:')
  })

  it('hides block that just started with opening tag', () => {
    const text = `שאלה ראשונה:

<!-- ui:interactive`
    expect(bufferInteractiveStream(text)).toBe('שאלה ראשונה:')
  })

  it('shows first completed block and hides second incomplete one', () => {
    const text = `שאלה 1:

<!-- ui:interactive
{"type":"choices","id":"q1","mode":"single","options":[{"id":"א","label":"yes"}]}
-->

שאלה 2:

<!-- ui:interactive
{"type":"choices","id":"q2","mode":"single","items":[{"id":"PARTIAL`
    const result = bufferInteractiveStream(text)
    // Should show everything up to the second incomplete block
    expect(result).toContain('שאלה 1:')
    expect(result).toContain('שאלה 2:')
    // First block's content is shown (it's complete)
    expect(result).toContain('"id":"q1"')
    // Second block's incomplete content is hidden
    expect(result).not.toContain('"id":"q2"')
    expect(result).not.toContain('PARTIAL')
  })

  it('shows everything when all blocks are complete', () => {
    const text = `שאלה 1:

<!-- ui:interactive
{"type":"choices","id":"q1","mode":"single","options":[]}
-->

שאלה 2:

<!-- ui:interactive
{"type":"confirm","id":"q2","yesLabel":"כן","noLabel":"לא"}
-->`
    expect(bufferInteractiveStream(text)).toBe(text)
  })

  it('handles text that contains <!-- but not ui:interactive', () => {
    const text = '<!-- some other comment --> hello'
    expect(bufferInteractiveStream(text)).toBe(text)
  })

  it('handles just the opening sequence arriving char by char', () => {
    // Simulates partial: "<!-- ui:int"
    const text = '<!-- ui:int'
    // This doesn't match "<!-- ui:interactive" fully so should pass through
    expect(bufferInteractiveStream(text)).toBe(text)
  })

  it('strips trailing whitespace before incomplete block', () => {
    const text = 'שלום   \n\n<!-- ui:interactive\n{"type":'
    const result = bufferInteractiveStream(text)
    expect(result).toBe('שלום')
  })
})
