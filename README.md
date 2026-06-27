# Breadcrumbs

Breadcrumbs is a privacy-first continual-learning assistant. It records active work sessions locally, processes screen context on-device, stores only sanitized memory in MongoDB Atlas, and suggests repeatable edits across Gmail, Slack, and VS Code after user approval.

## What It Does

- Starts an explicit local recording session from a small overlay bubble.
- Captures screenshots and OCR locally; raw frames and OCR text never upload.
- Receives structured activity from app connectors.
- Learns preferences from before/after edits, such as making outreach shorter, warmer, or more direct.
- Stores sanitized context, preferences, suggestion metadata, and embeddings in MongoDB Atlas.
- Applies approved edits through connectors instead of screen-coordinate automation.

## Project Layout

- `src/breadcrumbs`: Python local app, API, SQLite storage, privacy boundary, memory adapter, and overlay.
- `connectors/chrome-extension`: Gmail and Slack browser connector.
- `connectors/vscode`: VS Code connector.
- `tests`: Standard-library unit tests for privacy, storage, memory, and preference inference.
- `docs/architecture.md`: System boundaries and data flow.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
breadcrumbs init-db
breadcrumbs api
```

In another terminal:

```bash
source .venv/bin/activate
breadcrumbs overlay
```

Load the Chrome connector from `connectors/chrome-extension` using Chrome's "Load unpacked" developer flow, then paste the active session id into the extension popup.

## Privacy Boundary

Local only:

- screenshots
- raw OCR text
- full draft/message/file text
- detailed connector event logs

Allowed in MongoDB Atlas:

- app name
- timestamp
- task summary
- redacted text snippets
- learned preferences
- suggestion metadata
- deterministic demo embeddings

The sanitizer rejects screenshot and OCR fields before cloud writes.

## Tests

```bash
python3 -m unittest discover -s tests
```
