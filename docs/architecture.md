# Breadcrumbs Architecture

Breadcrumbs has three boundaries:

1. Local capture: screenshots, OCR text, raw connector text, and detailed app events stay on the laptop.
2. Sanitized memory: MongoDB Atlas receives summaries, redacted snippets, preferences, suggestion metadata, and embeddings.
3. Approved actions: connectors modify Gmail, Slack, or VS Code only after the local user approves a suggestion.

## Local Core

The Python core owns the session lifecycle, SQLite storage, preference inference, sanitization, MongoDB writes, and WebSocket updates. FastAPI exposes the local API on `127.0.0.1:8765`.

## Connectors

Connectors translate app-specific activity into a common document/edit model:

- `gmail`: Chrome extension observes compose fields and applies approved draft rewrites.
- `slack`: Chrome extension observes message composition in Slack workspaces.
- `vscode`: VS Code extension observes active file, selection, language, and local text edits.

The core does not special-case email behavior. It learns from before/after text and returns connector-neutral suggestions.

## Privacy Rule

Raw screenshot paths, screenshot bytes, OCR text, and full document text must not cross the cloud boundary. The `breadcrumbs.privacy` package enforces this before MongoDB writes.
