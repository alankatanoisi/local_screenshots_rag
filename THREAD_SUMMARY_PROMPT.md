# Thread Summary Prompt

Use this prompt in any Codex thread from this project when you want a concise summary that can be folded into the work log.

```text
Please summarize this thread for inclusion in the project work log.

Be concise but concrete. Use exactly this structure:

Thread name:
- [use the thread title exactly as shown in the app]

What was done:
- 3 to 8 short bullets covering actual work completed, not general discussion

Decisions made:
- short bullets
- if none, say `- None`

Open questions / unresolved items:
- short bullets
- if none, say `- None`

Files created or changed:
- short bullets with filenames only
- if unknown, say `- Unknown`

Commands or checks that mattered:
- short bullets
- if none, say `- None`

One-sentence takeaway:
- exactly one sentence

Important constraints:
- Do not include chain-of-thought.
- Do not include long explanations.
- Do not include anything outside this exact structure.
- Prefer specific facts over vague wording.
```

## How To Use It

- Open the thread you want summarized.
- Paste the prompt above into that thread.
- Copy the resulting summary back into the current day's work log.
- Repeat for each thread you want represented.
