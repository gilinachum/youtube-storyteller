---
name: document-export
description: Export content as downloadable documents — video scripts, research briefs, show notes, and plans. Use when the user asks to export, download, save, or share a document.
---

# Document Export

## When to Export

- User says "תייצא", "שמור", "הורד", "שלח לי" (export/save/download/send me)
- Conversation produced a complete deliverable (script, plan, research brief)
- User wants to share a session's output

## How

Use the `export_document` tool with:
- **filename** — descriptive Hebrew name with extension (.md, .txt, .docx concept)
- **content** — the full document text (Markdown formatted)

The tool returns a `file://` download link that renders as a card in the UI.

## Document Formats

Currently supported: **Markdown (.md)** and **plain text (.txt)**

Structure markdown documents with:
```markdown
# כותרת הסרטון

## סיכום
...

## מבנה הסרטון
### פתיחה (0:00-0:30)
...

### גוף (0:30-8:00)
...

### סיום (8:00-10:00)
...

## תיאור ליוטיוב
...

## תגיות
...
```

## Naming Convention

- Video scripts: `{video-topic}-script.md`
- Research briefs: `{topic}-research.md`
- Show notes: `{video-topic}-notes.md`
- Full plans: `{video-topic}-plan.md`

## Important

- Always include the complete content — don't truncate
- Use Hebrew for content, English for technical terms
- The download link is valid on-demand (no expiration concern)
- If content is very long, inform user of approximate length before exporting
