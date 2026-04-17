# zoom-assistant

A Python AI assistant for capturing notes. Two console tools share one codebase; both delegate multimodal reasoning to **Google Gemini**:

- **`notes-ocr`** — batch OCR a folder of class/meeting screenshots into a single Markdown file.
- **`zoom-notes`** *(planned)* — live Zoom meeting → Markdown transcript + screenshots.

## Prerequisites

- **Python 3.12** (pinned in `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** — package manager
- **[direnv](https://direnv.net/)** — loads secrets from `.envrc`
- A **Google Gemini API key** (free tier works for small folders; paid tier for larger runs)

## Setup

```bash
cp .envrc.example .envrc      # fill in your Gemini API keys
direnv allow                  # approve the env file
uv sync                       # install runtime + dev deps
```

## Configuration

Each Gemini *usage pattern* (OCR, transcription, polish) gets its own API key and model-fallback chain — so you can monitor usage and tune cost per purpose. All variables loaded by direnv from `.envrc`:

| Variable | Required | Purpose |
| --- | --- | --- |
| `NOTES_OCR_GEMINI_API_KEY` | for `notes-ocr` | image OCR calls |
| `ZOOM_NOTES_GEMINI_API_KEY` | for `zoom-notes` | audio transcription |
| `POLISH_GEMINI_API_KEY` | when `GEMINI_POLISH=1` | shared polish pass |
| `NOTES_OCR_GEMINI_MODELS` | no | model chain, comma-separated, priority order |
| `ZOOM_NOTES_GEMINI_MODELS` | no | as above |
| `POLISH_GEMINI_MODELS` | no | as above (defaults are cost-first) |
| `GEMINI_POLISH` | no | `1` enables polish (default), `0` skips |

A tool only requires its own primary key plus the polish key when polish is enabled. Each model chain falls through to the next entry on retryable failures (401/403/404/429/5xx/transport). See [.envrc.example](.envrc.example) for the template.

## Usage

### `notes-ocr`

```bash
notes-ocr [-s|--single-request] [--no-polish] [--dry-run] [-v|--verbose] /path/to/folder
```

OCR every image directly inside the folder (no recursion) and writes `<folder>/<folder-name>.md`, overwriting any existing file. Example:

```bash
notes-ocr "/Users/me/Downloads/Aulas/Grego I - Aula 04"
# → writes ".../Grego I - Aula 04/Grego I - Aula 04.md"
```

Flags:

- `-s/--single-request` — Pillow-stitch all images into one tall PNG and send a single OCR call (request-frugal mode for tight quotas).
- `--no-polish` — skip the polish pass; overrides `GEMINI_POLISH`.
- `--dry-run` — list images that would be processed without calling Gemini.
- `-v/--verbose` — DEBUG-level logging.

### `zoom-notes`

Not yet implemented. See [CLAUDE.md](CLAUDE.md) for the planned design.

## How it works

`notes-ocr` flow:

1. List image files (`.png`, `.jpg`, `.jpeg`) directly in the folder; sort oldest-first by file birthtime (mtime fallback).
2. Pack image `Part`s into multi-image batches of ~15 MB each — *or* stitch them all into one tall PNG (`-s` mode).
3. Send each batch to Gemini with the OCR prompt; response is a JSON `OcrResponse` with `##`/`###` sections.
4. Aggregate sections from all batches; render as `# <folder name>` + headings + bodies.
5. Run one polish pass over the full rendered markdown (when `GEMINI_POLISH=1`).
6. Write `<folder>/<folder-name>.md`.

Resilience:

- Each model chain falls through on retryable errors (auth / rate-limit / server / transport).
- Schema-validation failures retry once on the same model with a stricter prompt before falling through.
- Polish output is rejected if its word multiset differs from the input by more than 2% — the raw text is kept and a warning is logged.

## Modules

```
src/zoom_assistant/
├── cli.py                # console entry points
├── config.py             # env-var loading + per-tool factories
├── gemini.py             # Gemini client wrapper (chain, retry, polish)
├── image.py              # MIME detection + vertical stitching
├── markdown.py           # FolderNote + render_folder_note
├── notes_ocr/
│   ├── schema.py         # Pydantic OcrResponse + OCR prompt
│   └── pipeline.py       # list folder images → OCR → polish → emit
└── zoom_notes/           # (planned)
```

## Development

```bash
ruff format .
ruff check --fix .
mypy src
pytest
```

See [CLAUDE.md](CLAUDE.md) for project conventions and open design questions.

## License

MIT — see [LICENSE](LICENSE).
