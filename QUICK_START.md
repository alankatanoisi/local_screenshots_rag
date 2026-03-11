# ScreenMemory RAG Quick Start

This is the short version.

Important safety rule:

- This tool is designed to read your screenshots only.
- It stores its own database and cache here:
  `~/Library/Application Support/ScreenMemoryRAG/`
- It should **not** modify files inside:
  `/Users/alanman/ScreenMemoryData/screenshots`

## 1. Open Terminal

1. Press `Command + Space`
2. Type `Terminal`
3. Press `Return`

## 2. Go To The Project Folder

Paste this into Terminal:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
```

## 3. Set Up The Environment

Paste these commands one at a time:

```bash
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv pip install ".[dev,vec]"
```

## 3A. Safest Way To Run Commands

Use this pattern:

```bash
PYTHONPATH=src python -m screenmemory ...
```

## 4. Check Status

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory status
```

## 4A. Daily One-Liner To Open The App

If setup is already done, this is the easiest everyday launch command:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag" && swift build -c release && open "/Users/alanman/Documents/local_screenshots_rag/.build/arm64-apple-macosx/release/ScreenMemoryMenuBar"
```

Why this is better for low memory use:

- it does not open Xcode
- it avoids the heavy debugger process
- it launches the smaller `release` build

## 5. Index Recent Screenshots

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory index --recent-days 14 --batch-limit 100
```

## 6. OCR-Only Search

```bash
PYTHONPATH=src python -m screenmemory query "tuition email" --mode ocr-only
```

## 7. Semantic Search With Gemini

```bash
PYTHONPATH=src python -m screenmemory query "What research papers was I reading recently?" --mode semantic
```

## 8. Search A Specific Time Range

```bash
PYTHONPATH=src python -m screenmemory query "research paper" --mode ocr-only --start "2026-03-09 14:00" --end "2026-03-09 16:00"
```

## 9. Backfill Older History

```bash
PYTHONPATH=src python -m screenmemory backfill --batch-limit 200
```

## 10. Queue Batch Embeddings For Large History Runs

Use this if you want OCR indexing now and Gemini embeddings later in cheaper offline batches.

```bash
PYTHONPATH=src python -m screenmemory index-everything --batch-limit 200 --batch-embeddings
```

Submit a Gemini Batch API job:

```bash
PYTHONPATH=src python -m screenmemory embed-batch-submit --limit 500
```

Import finished batch results:

```bash
PYTHONPATH=src python -m screenmemory embed-batch-sync
```

If you want to stop all batch embedding work and clear the queue:

```bash
PYTHONPATH=src python -m screenmemory cancel-batches --all --clear-pending
```

## 11. Index Everything Safely In The Background

This is the new full-history command.

To install the dedicated background job:

```bash
PYTHONPATH=src python -m screenmemory index-everything --background --batch-limit 200
```

What it does:

- processes the full screenshot history in small chunks
- remembers where it left off
- keeps continuing in the background until it reaches the end
- does not rewrite the original screenshot files

To run just one resumable chunk manually:

```bash
PYTHONPATH=src python -m screenmemory index-everything --batch-limit 200
```

To remove the dedicated full-index background job:

```bash
PYTHONPATH=src python -m screenmemory remove-full-index-agent
```

## 12. Install Background Recent Indexing

```bash
PYTHONPATH=src python -m screenmemory install-launch-agent
```

To remove it later:

```bash
PYTHONPATH=src python -m screenmemory remove-launch-agent
```

## 13. Open The Menu Bar App

Paste this into Terminal:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag" && swift build -c release && open "/Users/alanman/Documents/local_screenshots_rag/.build/arm64-apple-macosx/release/ScreenMemoryMenuBar"
```

In Semantic mode, Gemini answers can show `[1]`, `[2]`, and similar citations.
Those footnotes map back to the screenshots the answer is referencing.

## 14. If Something Breaks

Try this first:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
uv pip install ".[dev,vec]"
PYTHONPATH=src python -m screenmemory status
```

If batch embeddings are stuck and you want a clean stop:

```bash
PYTHONPATH=src python -m screenmemory cancel-batches --all --clear-pending
```

If `tesseract` is missing:

```bash
brew install tesseract
```

For the full instructions, read:

- [USER_GUIDE.md](/Users/alanman/Documents/local_screenshots_rag/USER_GUIDE.md)
- [COMMANDS.md](/Users/alanman/Documents/local_screenshots_rag/COMMANDS.md)
