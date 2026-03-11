# ScreenMemory RAG

ScreenMemory RAG is a local-first screenshot search tool for macOS.

It does three main jobs:

1. It reads screenshots from `/Users/alanman/ScreenMemoryData/screenshots`.
2. It extracts text with OCR and stores search data in its own local database.
3. It lets you search either with:
   - `OCR Only` mode, which stays fully local except for your own terminal/app usage
   - `Semantic` mode, which uses Gemini for embeddings, time-filter parsing, and optional answer synthesis
4. In the menu bar app, Gemini answers can include numeric footnotes like `[1]` that map back to the retrieved screenshots they reference.

Important safety rule:

- This project is designed so it does **not** modify the screenshot files or write anything inside the screenshot folder tree.
- All generated data goes under `~/Library/Application Support/ScreenMemoryRAG/`.

## What gets created on your Mac

This app creates its own working files here:

- `~/Library/Application Support/ScreenMemoryRAG/screenmemory.db`
- `~/Library/Application Support/ScreenMemoryRAG/thumbnails/`
- `~/Library/Application Support/ScreenMemoryRAG/logs/`
- `~/Library/Application Support/ScreenMemoryRAG/batch/`

Your screenshot source folder is treated as read-only input.

## Current Stack / Services Used

This is the current working stack for the project.

- **Python CLI/package**
  - The Python side handles indexing, OCR, search, Gemini calls, and local database updates.
- **Swift menu bar app**
  - The Swift app gives you a lightweight macOS menu bar interface on top of the local search system.
- **Local OCR + local storage**
  - OCR text, metadata, thumbnails, logs, and batch job files stay on your Mac under the app support folder.
  - The main local database is SQLite, which is a small file-based database that does not need a separate server.
- **Gemini generation model**
  - Default model: `gemini-2.5-flash`
  - Used for semantic query planning, time-filter interpretation, and optional answer synthesis.
- **Gemini embedding model**
  - Default model: `gemini-embedding-001`
  - Used to turn OCR text and search queries into vectors for semantic retrieval.
- **Gemini batch embedding workflow**
  - Optional for larger backfills.
  - Lets you queue OCR chunks locally, submit them in batches, and sync finished embedding results later.

This section is intentionally brief for now and can be expanded later with more architecture details, provider choices, and data-flow notes.

## Current ScreenMemory Baseline Settings

These are the current ScreenMemory settings visible in the General tab screenshot that this project is being used with right now.

- Screenshot interval: `30 seconds`
- Compression: `Very (lower file size, lower quality)`
- Capture multi-monitor: `Off`
- Use high multi monitor resolution: `Off`
- Launch when macOS starts: `On`
- Always show dock icon: `On`
- Icon-only buttons: `Off`

Treat these as a current working baseline, not as final recommended settings for every setup.

## Before you run it

You will type the commands below into the **Terminal** app on your Mac.

If you have never opened Terminal before:

1. Press `Command + Space` to open Spotlight.
2. Type `Terminal`.
3. Press `Return`.
4. A window with a text prompt appears. That is where you paste the commands.

## Setup

In Terminal, paste these commands one at a time:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv pip install ".[dev,vec]"
```

If you want Gemini-powered semantic search, also set your API key:

```bash
export GEMINI_API_KEY="paste-your-google-api-key-here"
```

What success looks like:

- The install commands finish without a red error block.
- Running `PYTHONPATH=src python -m screenmemory status` shows the app support paths and database status.

## Easiest daily app launch

If setup is already done and you just want to run the app with the fewest moving parts, use this single copy-paste command in Terminal:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag" && swift build -c release && open "/Users/alanman/Documents/local_screenshots_rag/.build/arm64-apple-macosx/release/ScreenMemoryMenuBar"
```

Why this is the recommended daily launch:

- It does **not** open Xcode.
- It avoids Xcode's debugger memory overhead.
- It builds the smaller `release` version of the Swift app.

What success looks like:

- Terminal ends with `Build complete!`
- A small ScreenMemory icon appears in the macOS menu bar
- You do **not** need Xcode running for the app to stay open

## First index

To index only recent screenshots first:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory index --recent-days 14
```

To continue the older backfill:

```bash
PYTHONPATH=src python -m screenmemory backfill
```

To queue OCR chunks for later Gemini Batch API embeddings instead of embedding them immediately:

```bash
PYTHONPATH=src python -m screenmemory index-everything --batch-limit 200 --batch-embeddings
```

Then submit a batch job:

```bash
PYTHONPATH=src python -m screenmemory embed-batch-submit --limit 500
```

And later import finished results:

```bash
PYTHONPATH=src python -m screenmemory embed-batch-sync
```

If you want to stop all remaining batch embedding work later:

```bash
PYTHONPATH=src python -m screenmemory cancel-batches --all --clear-pending
```

What this cancels:

- open Gemini batch embedding jobs already submitted
- local chunks still waiting in the pending embedding queue

After it finishes, `screenmemory status` should show:

- `Open batch jobs: 0`
- `Pending embeddings: 0`

## Search from Terminal

OCR-only search:

```bash
PYTHONPATH=src python -m screenmemory query "tuition email from last Tuesday" --mode ocr-only
```

Semantic search with Gemini:

```bash
PYTHONPATH=src python -m screenmemory query "screenshots from last Tuesday between 2 PM and 4 PM where I was editing a school email" --mode semantic
```

In the menu bar app, semantic answers can show numeric citations. Clicking a citation selects the screenshot that answer sentence came from.

JSON output for other tools or the Swift app:

```bash
PYTHONPATH=src python -m screenmemory query "gmail tuition email" --mode ocr-only --json
```

## Install the background launch agent

This creates a macOS LaunchAgent that runs a short indexing pass every 2 minutes.

```bash
PYTHONPATH=src python -m screenmemory install-launch-agent
```

To remove it later:

```bash
PYTHONPATH=src python -m screenmemory remove-launch-agent
```

## Open the menu bar app

Use Terminal instead of Xcode for the lowest memory usage:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag" && swift build -c release && open "/Users/alanman/Documents/local_screenshots_rag/.build/arm64-apple-macosx/release/ScreenMemoryMenuBar"
```

You should see a small icon appear in the macOS menu bar.

If the app says it cannot find the CLI:

- Make sure you already ran the Python setup steps above.
- Make sure `uv` is installed at `/opt/homebrew/bin/uv`.
- Make sure this project is still located at `/Users/alanman/Documents/local_screenshots_rag`.

## Common failure modes

`tesseract: command not found`

- Install Tesseract with Homebrew: `brew install tesseract`

`No module named ...`

- Activate the virtual environment again with `source .venv/bin/activate`

`Semantic search says Gemini is not configured`

- Set `GEMINI_API_KEY` in Terminal before running the command.

`I want the menu bar app without the big Xcode memory spike`

- Use the Terminal launch command above instead of pressing Run in Xcode.
- Xcode plus its debugger can use far more memory than the release app binary itself.

`The app cannot create the database`

- Check that your Mac user account can write to `~/Library/Application Support/`
