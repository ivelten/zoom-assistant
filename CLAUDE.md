# CLAUDE.md

Project-level guidance for Claude Code. Loaded automatically in every session from this workspace.

## Project

A Python-based AI meeting/notes assistant. Two console entry points share a common package; all multimodal reasoning is delegated to **Google Gemini**:

1. `notes-ocr` — batch: image folders → per-folder Markdown notes.
2. `zoom-notes` — long-running: live Zoom meeting → Markdown transcript + screenshots.

`zoom-notes` runs **natively on the host** (macOS primary; Windows and Linux supported first-class). There is no devcontainer and no host/container split — the process has direct access to host audio devices and the screen.

## Environment

- **Python 3.12** (pinned in `.python-version`).
- **Package manager**: [uv](https://docs.astral.sh/uv/). Falls back to `pip install -e '.[dev]'`.
- **Formatter + linter**: [ruff](https://docs.astral.sh/ruff/) (replaces black / isort / flake8).
- **Type checker**: [mypy](https://mypy.readthedocs.io/) in strict mode.
- **Tests**: [pytest](https://docs.pytest.org/).
- **Secrets**: [direnv](https://direnv.net/) reads `.envrc` at the repo root. Copy `.envrc.example` → `.envrc`, fill in `GEMINI_API_KEY`, then `direnv allow`. `.envrc` is gitignored.

### Configuration

All knobs are environment variables loaded by direnv from `.envrc`. `src/zoom_assistant/config.py` parses and validates them at process start.

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `NOTES_OCR_GEMINI_API_KEY` | iff running `notes-ocr` | — | Auth token for the image OCR calls. |
| `ZOOM_NOTES_GEMINI_API_KEY` | iff running `zoom-notes` | — | Auth token for the audio transcription calls. |
| `POLISH_GEMINI_API_KEY` | iff `GEMINI_POLISH=1` | — | Auth token for the shared polish pass (used by both tools). |
| `NOTES_OCR_GEMINI_MODELS` | no | `gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite` | Model-fallback chain for image OCR. Quality-first. |
| `ZOOM_NOTES_GEMINI_MODELS` | no | `gemini-2.5-flash,gemini-2.0-flash,gemini-2.5-flash-lite` | Model-fallback chain for audio transcription. Quality-first. |
| `POLISH_GEMINI_MODELS` | no | `gemini-2.5-flash-lite,gemini-2.0-flash,gemini-2.5-flash` | Model-fallback chain for the shared polish pass. Cost-first — polish is text-only and high-volume. |
| `GEMINI_POLISH` | no | `1` | `1` enables the post-OCR / post-transcription polish pass (see each executable and [Polish pass](#polish-pass)). Set to `0` to skip it; `POLISH_GEMINI_API_KEY` / `POLISH_GEMINI_MODELS` then aren't required. |
| `ZOOM_NOTES_MIC_DEVICE` | no | auto | Optional PortAudio input index for the microphone. |
| `ZOOM_NOTES_LOOPBACK_DEVICE` | no | auto | Optional PortAudio input index for the system-audio loopback. |

**Model-chain semantics** (applies to all three `*_GEMINI_MODELS` vars): comma-separated model IDs in **priority order**. Every Gemini call tries the first model; on a retryable failure, the client falls through to the next. If every model fails, the call errors.

**Why per-purpose keys and chains?** Each of OCR / transcription / polish is a distinct Gemini usage pattern with different token/quota characteristics. Splitting lets you (a) monitor usage per purpose in the Google Cloud console and (b) tune model quality/cost per purpose — e.g. polish can run on cheaper Lite variants since it's text-only and high-volume, while OCR and transcription default to Flash for quality. `Config.for_notes_ocr()` and `Config.for_zoom_notes()` are tool-scoped factories; each only requires the key + chain relevant to the invoked tool (plus polish when enabled).

**Retryable failures** (fall through to next model): HTTP 401/403 (auth expired or revoked), 404 (model not available on this tier — exactly what the chain is for), 429 (rate limit / quota exhausted), 500/502/503/504 (server), connection errors. **Non-retryable**: HTTP 400 (malformed request — the same payload would fail on every model). Each call starts a fresh traversal of the chain; there is no cooldown timer — the chain's whole purpose is to keep working when one key/model is saturated or unavailable.

### Bootstrap

```bash
cp .envrc.example .envrc && direnv allow   # fill in the Gemini keys first
uv sync                                    # installs runtime + dev deps into .venv
```

## Repository layout

```text
.
├── pyproject.toml                 # uv-managed, Hatch build backend
├── .python-version                # 3.12
├── .envrc.example                 # template for direnv
├── .gitignore
├── CLAUDE.md
├── .claude/
│   └── settings.json              # Claude Code permissions for this repo
├── src/
│   └── zoom_assistant/
│       ├── __init__.py
│       ├── cli.py                 # Click entry points: notes_ocr_main, zoom_notes_main
│       ├── config.py              # env-var loading, fail-fast validation
│       ├── gemini.py              # google-genai client wrapper
│       ├── image.py               # Pillow decode / crop / encode helpers
│       ├── markdown.py            # Markdown emitters
│       ├── notes_ocr/             # executable 1 internals
│       │   ├── __init__.py
│       │   ├── schema.py          # Pydantic OcrResponse + OCR prompt
│       │   ├── walker.py          # directory traversal
│       │   └── pipeline.py        # OCR → crop → emit
│       └── zoom_notes/            # executable 2 internals
│           ├── __init__.py
│           ├── audio.py           # sounddevice capture + WAV chunking
│           ├── screen.py          # mss capture + perceptual hashing
│           ├── zoom_detect.py     # psutil-based process detection
│           └── pipeline.py        # orchestration, markdown output
└── tests/
```

## Executable 1 — `notes-ocr`

### Usage (notes-ocr)

```bash
notes-ocr /absolute/path/to/images
```

Exactly one positional arg: the root path. Exit non-zero on missing path.

### Behavior (notes-ocr)

1. Walk the given path recursively. Any directory containing one or more image files (`.png`, `.jpg`, `.jpeg`, case-insensitive) directly is a "note folder" and gets its own `notes/notes.md`. No merging across folders — subdirectories are walked independently and may become note folders themselves. Sibling folders are walked in sorted-name order; images within a folder are filename-sorted.
2. For each note folder, create a `notes/` subfolder containing `notes.md` — append-only; sections written in filename-sorted order for determinism.
3. For each source image, one Gemini `generate_content` call asks for a structured response:
   - Section headings detected by typographic hierarchy / column / card boxes → `##` / `###`.
   - Body text in natural reading order (handles multi-column layouts).
   - Any text embedded inside figures/diagrams is transcribed into the surrounding section; the figures themselves are not cropped or emitted separately.
4. In `notes.md`, each source image gets a section starting with `---`, then an ATX `#` heading with the original filename, then an italic line containing the image file's mtime in ISO-8601 with timezone (so re-runs don't re-stamp old notes with the current run's date). No YAML frontmatter. Per-image layout: `---` / `# <filename>` / `*<mtime>*` / Gemini headings (`##`/`###`) and polished body / asset links for any cropped figures.
5. **Append-only**. `notes.md` is opened in append mode; each run adds new sections at the end. No backup files. Re-running over the same folder produces duplicate sections by design — the user controls when to clear `notes.md`.
6. **Polish pass** (when `GEMINI_POLISH=1`, default). After OCR returns structured content for an image, the *body prose* of each section is sent through the shared [Polish pass](#polish-pass) to add punctuation and paragraph breaks without altering wording. Titles and headings bypass the polish step (they're short, already structured). If the polished output fails the word-count guardrail, keep the raw text and log a warning.

### Gemini model

Use the `GEMINI_MODELS` chain (default `gemini-2.5-flash,gemini-2.0-flash`); the wrapper iterates the chain on retryable failures. **JSON-schema validation failure** is handled in two steps: retry once on the *same* model with a stricter "JSON only, conform exactly to this schema" prompt; if that retry also fails to validate, fall through to the next model in the chain. No separate `2.5-pro` escalation path.

### Gemini call shape

```python
from google import genai
from google.genai import types

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        PROMPT,
    ],
    config=types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=OcrResponse,   # pydantic model
    ),
)
```

## Executable 2 — `zoom-notes`

### Usage (zoom-notes)

```bash
zoom-notes [OUTPUT_PATH]
```

If `OUTPUT_PATH` is omitted, write to the current working directory. Runs until SIGINT; flushes on shutdown.

### Behavior (zoom-notes)

1. Poll `psutil` (every ~2 s) for a running Zoom process (`zoom.us` / `Zoom.exe` / `zoom`); when found, begin capture. When the process ends, finalize the markdown and exit.
2. **Audio** — capture mic + system loopback via `sounddevice` (PortAudio). Mix both streams into a single mono 16 kHz PCM s16le buffer. Every **60 seconds**, flush the buffer to a WAV file and send it inline to Gemini `generate_content` for transcription. When `GEMINI_POLISH=1` (default), pipe the raw transcript through the shared [Polish pass](#polish-pass) before appending to `meeting-notes.md` with a timestamp header; on guardrail failure, keep the raw transcript and log a warning.
3. **Screen** — capture the primary display via `mss` every 3 s. Compute `imagehash.phash` on a downsampled grayscale Pillow image. If Hamming distance to the last kept frame exceeds a threshold (default 8), save the frame as `screen-<iso-timestamp>.png` and insert a relative link in `meeting-notes.md`.
4. `meeting-notes.md` opens in append mode; each session starts with a header containing date, Zoom PID, and audio device indices. Closing marker written on shutdown.
5. SIGINT flushes any in-flight audio chunk, writes a closing marker, and exits cleanly.

### Why `generate_content` (not the Live API)

User preference: fewer, larger requests with file-only output (no live readout). Gemini 2.5 `generate_content` accepts inline audio up to ~20 MB and returns diarized transcripts (best-effort — labels are `Speaker 1`, `Speaker 2`, …; Zoom participant identity is not available without the Zoom SDK). This keeps the client to plain HTTP/JSON and avoids websocket session management. For chunks larger than the inline limit, use the Files API (`client.files.upload(...)`).

### Gemini call shape (audio chunk)

```python
response = client.models.generate_content(
    model="gemini-2.5-flash",
    contents=[
        types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
        TRANSCRIBE_PROMPT,
    ],
)
```

### Host prerequisites per OS

- **macOS**
  - `brew install blackhole-2ch`
  - In **Audio MIDI Setup**, create a **Multi-Output Device** combining your speakers and BlackHole; set Zoom's output device to the multi-output so system audio is teed into BlackHole.
  - `sounddevice` enumerates BlackHole as an input device; the app opens it alongside the mic.
- **Windows**
  - WASAPI loopback is built into Windows; `sounddevice` can open the output device in loopback mode. Alternatively install [VB-Audio Virtual Cable](https://vb-audio.com/Cable/).
- **Linux**
  - Modern PipeWire/PulseAudio exposes monitor sources automatically (e.g. `…analog-stereo.monitor`). No extra driver needed.
- **All platforms**
  - First run prints enumerated audio devices; the user picks indices via `--mic-device N --loopback-device M` or env vars `ZOOM_NOTES_MIC_DEVICE` / `ZOOM_NOTES_LOOPBACK_DEVICE`.
  - `ffmpeg` is **not** required — capture is in-process via PortAudio and `mss`.

### Libraries

| Purpose | Package |
| --- | --- |
| Gemini API client | `google-genai` |
| Image decode / crop / encode | `Pillow` |
| Perceptual hashing | `imagehash` |
| Audio capture | `sounddevice` + `soundfile` + `numpy` |
| Screen capture | `mss` |
| Process detection | `psutil` |
| CLI | `click` |
| Logging / progress | `rich` |
| JSON schema for Gemini responses | `pydantic` |

## Polish pass

Shared by both executables when `GEMINI_POLISH=1` (default). One Gemini call per block of text, using the same model fallback chain as every other call.

**Purpose**: add punctuation and paragraph breaks to raw OCR/transcription output so the resulting `.md` file is readable. The AI must **not** change what was written or said.

**Prompt** (stored as a constant in `src/zoom_assistant/gemini.py`):

```text
You are a text formatter. Your only job is to add punctuation (periods, commas,
question marks, quotation marks), correct capitalization at sentence starts,
and split the text into paragraphs at natural boundaries.

STRICT RULES:
- Do NOT add, remove, replace, or rephrase any word.
- Preserve all numbers, proper nouns, technical terms, abbreviations, and
  domain-specific vocabulary exactly as given.
- Do NOT add headings, commentary, or any content of your own.
- Do NOT fix grammar if doing so would change any word.
- Output only the reformatted text, nothing else.

INPUT:
<RAW_TEXT>
```

**Word-count guardrail**: after the response returns, the client tokenises both input and output on whitespace, strips punctuation, and lowercases. If the multisets of tokens differ by more than **2%** (either direction), the polished output is rejected and the raw text is used instead, with a WARNING logged. This keeps the model honest about the "don't change the words" contract.

**Model fallback applies here too** — if the first model errors on the polish call, the client retries with the next model in `GEMINI_MODELS`. If every model errors, the raw text is kept and an error is logged; the executable does not abort.

## Build and run

```bash
uv sync                       # install
ruff format . && ruff check --fix .
mypy src
pytest
notes-ocr /abs/path/to/images
zoom-notes /abs/path/to/output
```

## Quality gates (run before committing)

```bash
ruff format .
ruff check --fix .
mypy src
pytest
```

## Secrets

The three per-purpose Gemini keys (`NOTES_OCR_GEMINI_API_KEY`, `ZOOM_NOTES_GEMINI_API_KEY`, `POLISH_GEMINI_API_KEY`) are read from the environment via direnv from `.envrc`. `src/zoom_assistant/config.py` must fail fast with a clear message when a required key is missing — required means "the primary key for the tool being invoked, plus `POLISH_GEMINI_API_KEY` iff `GEMINI_POLISH=1`". Never hard-code keys. Never commit `.envrc`.

## Conventions for Claude

- **Ask before creating files or scaffolding** the user hasn't approved. During planning phases, don't write code.
- **Python style**: type-hint all public surfaces, `from __future__ import annotations`, prefer dataclasses/pydantic for records, `pathlib.Path` over `os.path`, `logging` (or `rich.logging`) over `print`.
- No backwards-compat shims, no speculative abstractions — this project has no public callers.
- No comments for WHAT the code does; only non-obvious WHY.
- For new dependencies, run `uv add <pkg>` and verify the import works on Python 3.12 before committing.
- Permissions for development commands are pre-allowed in [.claude/settings.json](.claude/settings.json). `git push` and `git remote` mutations prompt. `rm -rf` on workspace parents, `gh auth`, and `git config --global` are denied outright.

## Git workflow

- **Never commit without asking.** After finishing a discrete task (feature landed, bug fixed, docs section done), proactively flag it as a good commit point and ask the user whether to commit. Never auto-commit, never silently run `git commit`.
- **Gitmoji prefix** on every commit subject line — use the UTF-8 emoji (not the `:shortcode:` form) as the first character, followed by a space and the short description. Reference: <https://gitmoji.dev/>. Common picks:

  | Emoji | Meaning |
  | --- | --- |
  | ✨ | new feature |
  | 🐛 | bug fix |
  | 📝 | documentation |
  | ♻️ | refactor (no behavior change) |
  | ⚡ | performance |
  | ✅ | tests |
  | 🔥 | remove code/files |
  | 🔧 | config / tooling |
  | 🚀 | deployment / release |
  | 🎉 | initial commit |

- **Committer identity**: always use the user's local `git config user.name` / `user.email`. Never pass `--author`, never modify `git config` values to change the committer.
- **Co-author trailer**: keep the default Claude Code trailer (`Co-Authored-By: Claude <model> <noreply@anthropic.com>`) at the end of every message — it already includes the model identifier, which is what the user wants. Do not remove or rewrite it.

Example:

```text
✨ add notes-ocr pipeline

Walks image folders, sends each to Gemini for structured OCR, and
emits one Markdown file per folder.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions (user decisions pending)

1. **`zoom-notes` frame cadence**: 3 s default OK, or slower / faster?
2. **Transcription prompt wording**: do you want speaker labels at all, or one flat running transcript?

## Settled decisions

- Native host execution (no containers, no split architecture).
- Python 3.12 + uv + ruff + mypy + pytest.
- **60-second** WAV chunks via `generate_content` (not the Live API).
- Screen-change detection in-process using `imagehash.phash` over `mss` frames.
- Host OS: macOS primary, Windows and Linux supported first-class.
- Gemini SDK: `google-genai` (the unified replacement for `google-generativeai`).
- **Per-purpose Gemini API keys and model chains**: `NOTES_OCR_GEMINI_API_KEY`+`NOTES_OCR_GEMINI_MODELS`, `ZOOM_NOTES_GEMINI_API_KEY`+`ZOOM_NOTES_GEMINI_MODELS`, `POLISH_GEMINI_API_KEY`+`POLISH_GEMINI_MODELS` — one pair per distinct usage pattern so billing/quota can be monitored *and* quality/cost tuned per purpose (primary chains default quality-first; polish defaults cost-first). `Config.for_notes_ocr()` and `Config.for_zoom_notes()` factories only require the pair(s) relevant to the invoked tool. `GeminiClient` takes one key + one model chain; the pipeline constructs one client per purpose.
- **Model fallback semantics**: comma-separated priority list; auth / rate-limit / server / network failures fall through, 400s hard-fail. Covers token/quota expiry mid-session. Applies to all three `*_GEMINI_MODELS` vars.
- **Schema-validation failures** in OCR calls: retry once on the *same* model with a stricter prompt; if still invalid, fall through to the next model in the chain. No separate `2.5-pro` escalation path.
- **Polish pass** (`GEMINI_POLISH=1` by default): every OCR body and every transcript chunk is reformatted by a strict "punctuation and paragraphs only" Gemini prompt with a ≤2% word-count guardrail; content is never changed.
- **`notes-ocr` output format**: ATX headings, no YAML frontmatter; `notes.md` is **append-only** (no `.bak`). Per-image section: `---` / `# <original-filename>` / `*<image-mtime ISO-8601 with tz>*` / Gemini headings + polished body / asset links.
- **`notes-ocr` walker**: every directory containing image files directly becomes its own note folder with its own `notes.md`. No cross-folder merging; subdirectories are walked independently. Sibling folders walked in sorted-name order; images within a folder filename-sorted.
- **`notes-ocr` concurrency**: `--jobs N` CLI flag, default `min(8, os.cpu_count() or 1)`. Folders processed sequentially; images parallel within a folder (rate-limit friendly).
- **`notes-ocr` scope**: text-only OCR for now. Figures embedded in images have their text transcribed into the surrounding section but are not cropped out or linked as assets.
