# AGENTS.md

## What this is

Nekto.me chat automator. Playwright (Python) drives Chrome to automate Russian chat conversations on nekto.me. **Windows-only** (`winsound`, `.bat` scripts).

The entire bot lives in `CHat/bot.py` (~1280 lines). It is fully self-contained — no imports from `brain.py`, `observer.py`, or `executor.py`.

## Key commands

```powershell
cd CHat
pip install -r requirements.txt
playwright install chromium
copy .env.example .env    # edit USER_DATA_DIR
.\start-chrome.bat        # kills ALL chrome.exe, launches on port 9222
python bot.py             # or: py bot.py (via run.bat)
```

## Architecture

`bot.py` is organized as a **3-stage pipeline**. Each stage is an async function that returns `count` (success) or `None` (end chat):

```python
stages = [stage_greeting, stage_names, stage_free_chat]
for stage_fn in stages:
    result = await stage_fn(page, count, chat_messages, state)
    if result is None:
        break
    count = result
```

| Stage | Function | Goal |
|-------|----------|------|
| 1 | `stage_greeting()` | Send "привет", ask "сколько лет", validate age in `[17, 18, 19]` |
| 2 | `stage_names()` | Wait for partner to ask name or say something; if they ask age/and_you → answer "19" first, then ask "Максим, тебя?" |
| 3 | `stage_free_chat()` | Infinite loop: respond to questions, handle dismissive/ukrainian/muslim triggers |

**Stage 2 flow**:
1. Wait up to 20s for partner's first message after age is known
2. If partner asks age or says "а тебе"/"тебе?" → answer "19", then wait for another message before name exchange
3. If partner introduces themselves or asks name → send "Максим" or "Максим, тебя?" immediately
4. If timeout → send "Максим, тебя?" proactively
5. Then wait up to 15s for partner's name response

**`ChatState` dataclass** tracks conversation state between stages: `partner_name`, `partner_age`, `said_19`, `name_sent`, `stage`.

**Pattern matching is substring-based** (`if p in t.lower()`), not regex. This means:
- Patterns must account for Russian typos/misspellings explicitly
- Short substrings like "тебя" appear in unrelated phrases — use exact forms like "тебя?", "тебе?", "а тебя?" separately
- Adding new patterns: test against edge cases where the substring appears in unrelated words

**Bot persona**: hardcoded as "Максим", age 19. Gender check via `_partner_name_received()` — if partner already shared a name (single capitalized word or self-introduction), answers "Максим" without asking back.

**TTS**: optional Piper TTS with ONNX voice models in `CHat/voices/`. Worker thread synthesizes partner messages (female) and sent messages (male). Degrades gracefully if piper/sounddevice unavailable.

## Important files

| File | Role |
|------|------|
| `CHat/bot.py` | **The** entrypoint. All logic lives here. |
| `CHat/config.py` | Env config — `USER_DATA_DIR` and `REMOTE_DEBUGGING_PORT` used by bot.py. `LLM_API_URL`/`LLM_MODEL` are dead (LLM integration not wired). |
| `CHat/voices/` | ONNX voice models for Piper TTS |
| `CHat/start-chrome.bat` | Launches Chrome with `--remote-debugging-port=9222`. Kills ALL chrome.exe first. |
| `CHat/run.bat` | Just `py bot.py` |

**Unused files** (legacy drafts, not imported by bot.py):
- `CHat/brain.py`, `CHat/observer.py`, `CHat/executor.py` — OOP modules from an earlier design
- `QWEN.md` — references a `ChatLLM/` subproject that does not exist
- `CHat/README.md` — describes Ollama/LLM integration that is not wired

## Gotchas

- **`start-chrome.bat` kills ALL chrome.exe** — runs `taskkill /F /IM chrome.exe`. Close all browser windows first.
- **Two Chrome instances**: `start-chrome.bat` starts Chrome on port 9222, then `bot.py` calls `launch_persistent_context()` which starts another. They may conflict on port or profile lock.
- **`winsound`** — Windows-only module. Bot will crash on Linux/macOS.
- **No lint, no typecheck** configured in this repo.
- **`config.py` has selectors** in a `SELECTORS` dict (line ~28) but only the unused OOP modules reference it. All active selectors are hardcoded at the top of `bot.py` (lines 84–93). Edit `bot.py` directly.
- **Chat logs** written to `chat_logs/` relative to CWD (not relative to `bot.py`). Run from `CHat/` to get `CHat/chat_logs/`.
- **`DEBUG = True`** hardcoded in bot.py (line 13) — all `[DEBUG]` output goes to stdout.
- **Response time on timeout is always 0** — `wait_for_partner_msg` returns `(None, count, 0)` on timeout, not the actual elapsed time.

## Testing

`CHat/test_bot.py` — 136 unit tests on pure logic (patterns, filters, helpers). Run:

```powershell
cd CHat
$env:PYTHONIOENCODING='utf-8'; python test_bot.py
```

**All tests MUST pass before and after any change to bot.py.** If a test fails after your change — revert.

## Workflow Protocol

1. **Git commit before changes** — always commit current working state before editing
2. **Targeted changes only** — make exactly what's requested, don't touch working parts
3. **Run tests after changes** — `python test_bot.py`, all 133 must pass
4. **Changelog** — record changes in `CHat/CHANGELOG.md`
5. **Don't rewrite** — edit existing code, don't rewrite functions from scratch
