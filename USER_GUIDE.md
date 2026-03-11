# ScreenMemory RAG User Guide

This guide explains how to use your screenshot search tool on your Mac.

The goal of this tool is simple:

- It reads your existing screenshots from:
  `/Users/alanman/ScreenMemoryData/screenshots`
- It extracts text from them with OCR.
- It lets you search them in two ways:
  - `OCR Only`: plain text search on extracted screenshot text
  - `Semantic`: Gemini-powered meaning-based search with an optional AI answer

Most important safety rule:

- This tool is designed to **not modify your screenshot files**.
- It reads them.
- It stores its own database, thumbnail cache, and logs somewhere else:
  `~/Library/Application Support/ScreenMemoryRAG/`

## 1. What You Need

You need:

- A Mac
- The `Terminal` app
- This project folder:
  `/Users/alanman/Documents/local_screenshots_rag`
- Your screenshots already being saved here:
  `/Users/alanman/ScreenMemoryData/screenshots`

Optional but useful:

- The Apple Swift toolchain, if you want to run the menu bar app
- A Gemini API key, if you want semantic search and AI answers

## 2. How To Open Terminal

If you are brand new to this:

1. Press `Command + Space` on your keyboard.
2. This opens `Spotlight`, which is Apple’s search bar.
3. Type `Terminal`.
4. Press `Return`.

What you should see:

- A window opens.
- It usually has a prompt ending in `$` or `%`.
- That is where you paste commands.

Do **not** paste Terminal commands into:

- Spotlight
- Safari’s address bar
- Chrome’s address bar
- Notes
- TextEdit

Paste them only into the Terminal window.

## 3. Go Into The Project Folder

Copy and paste this into Terminal, then press `Return`:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
```

What success looks like:

- Terminal does not show an error.
- Your prompt moves to a new line.

If you see `No such file or directory`:

- The folder path is different than expected.
- Open Finder and confirm the folder is exactly named:
  `local_screenshots_rag`

## 4. Set Up The Python Environment

This project uses a Python virtual environment.

Plain-English definition:

- A `virtual environment` is a private little Python workspace for one project, so it does not mix packages with other projects on your Mac.

Paste these commands into Terminal one at a time:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
uv python install 3.12
uv venv --python 3.12
source .venv/bin/activate
uv pip install ".[dev,vec]"
```

## 4A. The Safest Command Pattern

Use this pattern whenever possible:

```bash
PYTHONPATH=src python -m screenmemory ...
```

Example:

```bash
PYTHONPATH=src python -m screenmemory status
```

What success looks like:

- You do not get a red error.
- The install finishes and returns you to the prompt.

If you see `uv: command not found`:

- `uv` is missing on your Mac.
- Install it with Homebrew first:

```bash
brew install uv
```

Then repeat the setup commands above.

## 5. Confirm The Tool Works

Paste this into Terminal:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory status
```

What success looks like:

- You see lines showing:
  - screenshot root
  - app support directory
  - database path
  - indexed screenshot count
  - indexed chunk count

The important folders are:

- Screenshot source:
  `/Users/alanman/ScreenMemoryData/screenshots`
- App data:
  `/Users/alanman/Library/Application Support/ScreenMemoryRAG`

## 5A. Daily One-Liner To Open The Menu Bar App

If the project is already set up and you just want to open the app with one paste, use this in Terminal:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag" && swift build -c release && open "/Users/alanman/Documents/local_screenshots_rag/.build/arm64-apple-macosx/release/ScreenMemoryMenuBar"
```

Plain-English explanation:

- `swift build -c release`
  builds the Swift app in a smaller production-style mode
- `open .../ScreenMemoryMenuBar`
  tells macOS to launch that built app

Why this is the recommended daily launch:

- it avoids opening Xcode
- it avoids Xcode's debugger memory usage
- it keeps the launch steps short and repeatable

## 6. Your Gemini API Key

Your project already has a local `.env` file so the app can read your Gemini API key automatically.

That means:

- You do **not** need to paste the key every time into Terminal.
- Semantic mode should use the local key automatically.

Important:

- The `.env` file is ignored by git, so it should not be committed accidentally.

## 7. First Indexing Run

Indexing means:

- The app scans screenshot files
- Runs OCR
- Stores extracted text and metadata
- Optionally stores embeddings for semantic search
- Or, if you choose batch mode, marks chunks as `pending` so Gemini Batch API can embed them later

For a first smaller run, paste this:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory index --recent-days 14 --batch-limit 100
```

What this does:

- Looks at recent screenshots first
- Indexes up to 100 matching screenshots in this pass
- Writes data only to the app’s own database

What success looks like:

- You see JSON output like:
  - `processed`
  - `skipped`
  - `errors`
  - `last_indexed_path`

Important safety reminder:

- This does **not** rewrite the screenshot JPEGs.
- It only reads them.

## 8. Continue Backfilling Older History

Once recent screenshots are searchable, you can index older history too.

Paste this:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory backfill --batch-limit 200
```

You can run that command again later as many times as you want.

Think of it as:

- `index` = recent-first pass
- `backfill` = older history pass

## 8B. Batch Embeddings For Big Backfills

Use this when you want:

- OCR and metadata indexed right away
- Gemini embeddings generated later in offline batches
- better fit for large history runs

Step 1: queue pending embeddings while indexing:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory index-everything --batch-limit 200 --batch-embeddings
```

Step 2: submit a Gemini Batch API job:

```bash
PYTHONPATH=src python -m screenmemory embed-batch-submit --limit 500
```

What success looks like:

- you see JSON with a `batch_id`
- you see a local request file path under:
  `~/Library/Application Support/ScreenMemoryRAG/batch/requests/`

Step 3: later, import completed batch results:

```bash
PYTHONPATH=src python -m screenmemory embed-batch-sync
```

Important:

- this still does **not** modify the source screenshot files
- it only creates request/result files in the app's own batch folder
- semantic search only uses chunks whose embeddings are fully imported

If you later decide you want to stop all remaining batch work:

```bash
PYTHONPATH=src python -m screenmemory cancel-batches --all --clear-pending
```

That command does two things:

- cancels open batch jobs already sent to Gemini when the SDK can do so
- clears local pending embedding work so your queue drops back to zero

## 8A. Index Everything Safely In The Background

This is the dedicated full-history indexing command.

Use this when you want:

- the app to eventually cover the whole screenshot archive
- the work to happen in chunks
- a lightweight background approach instead of one giant long-running scan

To install the dedicated full-index background job:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory index-everything --background --batch-limit 200
```

What this does:

- creates a dedicated macOS LaunchAgent for full-history indexing
- runs short chunked passes every 2 minutes
- remembers the last completed cursor position in the database
- continues until it reaches the end of the screenshot history

To run only one resumable chunk manually:

```bash
PYTHONPATH=src python -m screenmemory index-everything --batch-limit 200
```

To remove the dedicated full-index background job:

```bash
PYTHONPATH=src python -m screenmemory remove-full-index-agent
```

This is different from the normal recent indexing agent:

- `install-launch-agent`
  - keeps recent screenshots fresh
- `index-everything --background`
  - walks through the entire historical archive until complete

## 9. OCR-Only Search

Use this when you want:

- fast search
- local text search
- no Gemini AI answer

Example:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory query "tuition email" --mode ocr-only
```

What you should see:

- a list of results
- timestamps
- file paths
- OCR snippets
- thumbnail cache paths

This mode searches the OCR text only.

It does **not**:

- ask Gemini to interpret your question
- generate embeddings for the query
- produce a chatbot-style answer

## 10. Semantic Search

Use this when you want:

- meaning-based search
- more flexible natural language
- optional Gemini-generated answer

Example:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory query "What biomedical papers was I reading recently?" --mode semantic
```

What this mode can do:

- interpret broader meaning
- try to understand time phrases like `recently`
- search using embeddings
- return a Gemini answer plus matching screenshots

This mode depends on:

- your Gemini API key
- already indexed screenshots
- embeddings having been created for indexed OCR chunks

In the menu bar app, Gemini answers can include footnotes like `[1]` and `[2]`.
Those citations map back to the retrieved screenshots that the answer is using as evidence.

## 11. Search In JSON Format

JSON is a structured text format that apps use to exchange data.

Use this if you want a machine-readable result:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory query "gmail tuition email" --mode ocr-only --json
```

You will see fields like:

- `mode`
- `parsed_query`
- `filters_applied`
- `answer`
- `results`

## 12. Search With Explicit Time Filters

You can also provide start and end times yourself.

Example:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory query "research paper" --mode ocr-only --start "2026-03-09 14:00" --end "2026-03-09 16:00"
```

This is useful when you want exact control.

## 13. Sorting Results

You can sort results with:

- `relevance`
- `newest`
- `oldest`

Example:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory query "research paper" --mode semantic --sort newest
```

## 14. Run The Menu Bar App

The menu bar app is the little app that sits near the top-right of your Mac screen in the menu bar.

To open it with the lowest memory usage, paste this into Terminal:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag" && swift build -c release && open "/Users/alanman/Documents/local_screenshots_rag/.build/arm64-apple-macosx/release/ScreenMemoryMenuBar"
```

What success looks like:

- A small icon appears in your Mac menu bar.
- Clicking it opens the search UI.
- Xcode does **not** need to be open.

Inside the menu bar app you should see:

- a search box
- a mode switch:
  - `Semantic`
  - `OCR Only`
- result list
- small thumbnail strip
- larger preview area
- buttons to:
  - open the screenshot
  - reveal it in Finder
  - copy the path

## 15. Background Indexing

You can install a macOS LaunchAgent.

Plain-English definition:

- A `LaunchAgent` is a small macOS background helper that can run a command on a schedule.

To install it:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory install-launch-agent
```

What it does:

- runs a short recent indexing pass every 2 minutes
- avoids a heavy always-running watcher

To remove it:

```bash
PYTHONPATH=src python -m screenmemory remove-launch-agent
```

To see the full-history cursor status:

```bash
PYTHONPATH=src python -m screenmemory status
```

You will see fields for:

- full index cursor epoch
- full index cursor path
- full index completed at

## 16. Where The App Stores Its Own Files

This tool stores its own data here:

- Database:
  `~/Library/Application Support/ScreenMemoryRAG/screenmemory.db`
- Thumbnail cache:
  `~/Library/Application Support/ScreenMemoryRAG/thumbnails/`
- Logs:
  `~/Library/Application Support/ScreenMemoryRAG/logs/`

This separation is important because it helps protect the original screenshot system.

## 17. Common Problems And Fixes

### Problem: `screenmemory: command not found`

Fix:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
uv pip install ".[dev,vec]"
```

Then try:

```bash
PYTHONPATH=src python -m screenmemory status
```

### Problem: `tesseract: command not found`

Fix:

```bash
brew install tesseract
```

Then retry your command.

### Problem: semantic search fails

Possible causes:

- Gemini API key missing
- API key invalid
- temporary Google API error
- no semantic chunks indexed yet

Try:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory index --recent-days 3 --batch-limit 20
PYTHONPATH=src python -m screenmemory status
```

### Problem: results seem incomplete

Usually this means:

- not enough screenshots have been indexed yet
- backfill has not gone far enough yet

Fix:

```bash
PYTHONPATH=src python -m screenmemory backfill --batch-limit 500
```

Then run your search again.

### Problem: the menu bar app opens but shows an error

Possible causes:

- the Python environment is not installed
- the CLI is missing
- the database does not exist yet

Fix:

1. Go back to Terminal.
2. Activate the virtual environment.
3. Run:

```bash
PYTHONPATH=src python -m screenmemory status
PYTHONPATH=src python -m screenmemory index --recent-days 14 --batch-limit 50
```

Then run the one-line Terminal launch command again.

### Problem: batch jobs are still open and I want to stop them

Run this in Terminal:

```bash
cd "/Users/alanman/Documents/local_screenshots_rag"
source .venv/bin/activate
PYTHONPATH=src python -m screenmemory cancel-batches --all --clear-pending
```

What success looks like:

- `screenmemory status` later shows:
  - `Open batch jobs: 0`
  - `Pending embeddings: 0`

## 18. Good Beginner Command Examples

Search local OCR only:

```bash
PYTHONPATH=src python -m screenmemory query "notion notes" --mode ocr-only
```

Search semantically:

```bash
PYTHONPATH=src python -m screenmemory query "What papers or studies was I reading yesterday?" --mode semantic
```

Search newest first:

```bash
PYTHONPATH=src python -m screenmemory query "gmail draft" --mode ocr-only --sort newest
```

Search a time range:

```bash
PYTHONPATH=src python -m screenmemory query "research article" --mode semantic --start "2026-03-09 09:00" --end "2026-03-09 11:30"
```

## 19. Safest Way To Think About This Tool

This tool has three separate parts:

1. Your original screenshots
   - these are the source files
   - they should stay untouched

2. The app’s own database and cache
   - this is where OCR text, metadata, embeddings, and thumbnails go

3. The search interface
   - Terminal commands
   - menu bar app

That separation is intentional.

It is the main design decision that helps avoid interfering with your ScreenMemory screenshot system.

## 20. Recommended Everyday Workflow

For day-to-day use, a simple pattern is:

1. Open Terminal.
2. Go to the project folder.
3. Activate the virtual environment.
4. Run a recent indexing pass:

```bash
PYTHONPATH=src python -m screenmemory index --recent-days 3 --batch-limit 100
```

5. Then search:

```bash
PYTHONPATH=src python -m screenmemory query "What research papers was I reading?" --mode semantic
```

Or, for a local-only search:

```bash
PYTHONPATH=src python -m screenmemory query "paper title keyword" --mode ocr-only
```

If you want, this can be made even easier later with:

- a double-click app bundle
- a global hotkey
- automatic startup at login
- a one-button “index now” control in the menu bar app
