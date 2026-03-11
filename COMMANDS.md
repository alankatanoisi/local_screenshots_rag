# ScreenMemory RAG Command List

Use this at the start of any new Terminal window:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
```

Safest command style:

```bash
PYTHONPATH=src python -m screenmemory ...
```

Daily one-liner to build and open the menu bar app without Xcode:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag" && swift build -c release && open "/Users/alanman/Documents/local_screenshots_rag/.build/arm64-apple-macosx/release/ScreenMemoryMenuBar"
```

## Setup

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
uv python install 3.12
uv venv --python 3.12 --clear
source .venv/bin/activate
uv pip install ".[dev,vec]"
```

## Status

```bash
PYTHONPATH=src python -m screenmemory status
```

```bash
PYTHONPATH=src python -m screenmemory status --json
```

## Recent Indexing

```bash
PYTHONPATH=src python -m screenmemory index --recent-days 14 --batch-limit 100
```

```bash
PYTHONPATH=src python -m screenmemory index --recent-days 14 --batch-limit 100 --skip-embeddings
```

```bash
PYTHONPATH=src python -m screenmemory index --recent-days 14 --batch-limit 100 --batch-embeddings
```

## Backfill

```bash
PYTHONPATH=src python -m screenmemory backfill --batch-limit 200
```

```bash
PYTHONPATH=src python -m screenmemory backfill --batch-limit 200 --skip-embeddings
```

```bash
PYTHONPATH=src python -m screenmemory backfill --batch-limit 200 --batch-embeddings
```

## Full-History Indexing

```bash
PYTHONPATH=src python -m screenmemory index-everything --batch-limit 200
```

```bash
PYTHONPATH=src python -m screenmemory index-everything --batch-limit 200 --skip-embeddings
```

```bash
PYTHONPATH=src python -m screenmemory index-everything --background --batch-limit 200
```

```bash
PYTHONPATH=src python -m screenmemory index-everything --batch-limit 200 --batch-embeddings
```

```bash
PYTHONPATH=src python -m screenmemory index-everything --background --batch-limit 200 --batch-embeddings
```

```bash
PYTHONPATH=src python -m screenmemory remove-full-index-agent
```

## Batch Embeddings

```bash
PYTHONPATH=src python -m screenmemory embed-batch-submit --limit 500
```

```bash
PYTHONPATH=src python -m screenmemory embed-batch-sync
```

```bash
PYTHONPATH=src python -m screenmemory embed-batch-sync --batch-id "batches/1234567890"
```

```bash
PYTHONPATH=src python -m screenmemory cancel-batches --all --clear-pending
```

## Recent Background Indexing

```bash
PYTHONPATH=src python -m screenmemory install-launch-agent
```

```bash
PYTHONPATH=src python -m screenmemory remove-launch-agent
```

## OCR-Only Search

```bash
PYTHONPATH=src python -m screenmemory query "tuition email" --mode ocr-only
```

```bash
PYTHONPATH=src python -m screenmemory query "gmail draft" --mode ocr-only --sort newest
```

```bash
PYTHONPATH=src python -m screenmemory query "research paper" --mode ocr-only --start "2026-03-09 14:00" --end "2026-03-09 16:00"
```

```bash
PYTHONPATH=src python -m screenmemory query "gmail tuition email" --mode ocr-only --json
```

## Semantic Search

```bash
PYTHONPATH=src python -m screenmemory query "What research papers was I reading recently?" --mode semantic
```

```bash
PYTHONPATH=src python -m screenmemory query "What papers or studies was I reading yesterday?" --mode semantic --sort newest
```

```bash
PYTHONPATH=src python -m screenmemory query "research article" --mode semantic --start "2026-03-09 09:00" --end "2026-03-09 11:30"
```

```bash
PYTHONPATH=src python -m screenmemory query "What biomed research papers was I viewing?" --mode semantic --no-answer
```

```bash
PYTHONPATH=src python -m screenmemory query "What research papers was I reading recently?" --mode semantic --json
```

Semantic answers in the menu bar app can include numeric footnotes like `[1]`.
Each footnote maps back to one of the retrieved screenshots.

## Repair

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
uv venv --python 3.12 --clear
source .venv/bin/activate
uv pip install ".[dev,vec]"
```

```bash
PYTHONPATH=src python -m screenmemory status
```

cd "/Users/alanman/Documents/local_screenshots_rag"
uv venv --python 3.12 --clear
source .venv/bin/activate
uv pip install ".[dev,vec]"
