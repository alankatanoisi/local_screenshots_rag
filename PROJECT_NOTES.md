# Project Notes

This file is the internal working note for the project.

Use it as the first place to record short-lived but important project context that should survive across Codex threads.

## Current Status

- Project working title: `ScreenMemory RAG`
- Naming is still open and intentionally undecided.
- Public GitHub repo exists and is live.
- Main public landing page: `README.md`
- Public README snapshots live in `readme-history/`

## What This Project Is

- A local-first macOS screenshot search tool.
- It indexes screenshots from a user-selected screenshot folder.
- It extracts OCR text locally.
- It stores search/index data in its own local app-support area.
- It supports:
  - OCR-only search
  - semantic search with Gemini assistance
- It includes a Swift menu bar app on top of the Python indexing/search system.

## Public / Private Boundary

- Treat the GitHub repo as public-facing by default.
- Keep secrets out of tracked files.
- Keep machine-specific or personal notes out of the public README unless they are intentionally generalized.
- The public README should stay safe to publish at all times.
- If private notes are needed later, keep them in a separate ignored file rather than in `README.md`.

## Documentation Structure

- `README.md`
  - Current public landing page.
- `readme-history/`
  - Archived public README editions.
- `QUICK_START.md`
  - Short setup and getting-started path.
- `USER_GUIDE.md`
  - Longer human-facing usage documentation.
- `COMMANDS.md`
  - Command reference and copy-paste workflows.
- `PROJECT_NOTES.md`
  - Internal project truth for future threads.
- `ROADMAP.md`
  - Near-term and medium-term priorities.
- `DECISIONS.md`
  - Important choices and why they were made.

## Working Conventions

- Keep one primary `README.md` at the repo root.
- Archive meaningful README milestones in `readme-history/` using the pattern:
  - `README-vX-YYYY-MM-DD.md`
- Prefer small commits with understandable messages.
- Prefer public-safe wording in documentation unless a file is explicitly private and ignored.
- Keep the current repo/folder name until a better name clearly wins.

## Good Starter Prompt For Future Threads

Use something like this when opening a new Codex thread:

```text
Workspace is `/Users/alanman/Documents/local_screenshots_rag`.

Please read `PROJECT_NOTES.md` and `README.md` first.

If relevant, also read:
- `USER_GUIDE.md`
- `COMMANDS.md`
- `ROADMAP.md`
- `DECISIONS.md`

Assume the repo is public-facing unless I say otherwise.
```

## Notes To Update Over Time

Update this file when any of these change:

- project/app/repo naming direction
- what is public vs private
- documentation structure
- current priorities
- major workflow conventions
- where screenshots/assets should live
- any recurring "do not touch" or "be careful with this" rules
