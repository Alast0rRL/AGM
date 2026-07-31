# AGENTS.md

## What this is

Nekto.me chat automator. Playwright (Python) drives Chrome to automate Russian chat conversations on nekto.me. **Windows-only** (`winsound`, `msvcrt`, `.bat` scripts).

The entire bot lives in `bot.py` (~2270 lines). It is fully self-contained.

## Key commands

```powershell
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
1. Wait indefinitely for partner's message after age is known
2. If partner asks age or says "а тебе"/"тебе?" → answer "19", then continue waiting
3. If partner introduces themselves or asks name → send "Максим" or "Максим, тебя?" immediately
4. Then wait up to 15s for partner's name response

**`ChatState` dataclass** tracks conversation state between stages: `partner_name`, `partner_age`, `said_19`, `name_sent`, `stage`, `last_own_msg`, `started_at`, `marked_success`.

**Pattern matching is substring-based** (`if p in t.lower()`), not regex. This means:
- Patterns must account for Russian typos/misspellings explicitly
- Short substrings like "тебя" appear in unrelated phrases — use exact forms like "тебя?", "тебе?", "а тебя?" separately
- Adding new patterns: test against edge cases where the substring appears in unrelated words

**Bot persona**: hardcoded as "Максим", age 19. Gender check via `_partner_name_received()` — if partner already shared a name (single capitalized word or self-introduction), answers "Максим" without asking back.

**TTS**: optional Piper TTS with ONNX voice models in `voices/`. Worker thread synthesizes partner messages (female) and sent messages (male). Degrades gracefully if piper/sounddevice unavailable.

**Successful-dialogue logging**: only successful chats are saved — press `S` in console to mark current chat (outcome `manual`), or auto-criteria `SUCCESS_MIN_MSGS`/`SUCCESS_MIN_SEC` (outcome `auto`). Logs go to `chat_logs/success/`, index to `chat_logs/summary.csv`. Decision logic in `_chat_outcome()`; `save_chat_log(messages, state)` returns `None` when chat is not successful.

## Important files

| File | Role |
|------|------|
| `bot.py` | **The** entrypoint. All logic lives here. |
| `config.py` | Env config — only `USER_DATA_DIR` and `REMOTE_DEBUGGING_PORT`, both used by bot.py. |
| `voices/` | ONNX voice models for Piper TTS |
| `start-chrome.bat` | Launches Chrome with `--remote-debugging-port=9222`. Kills ALL chrome.exe first. |
| `run.bat` | Just `py bot.py` |

## Gotchas

- **`start-chrome.bat` kills ALL chrome.exe** — runs `taskkill /F /IM chrome.exe`. Close all browser windows first.
- **Two Chrome instances**: `start-chrome.bat` starts Chrome on port 9222, then `bot.py` calls `launch_persistent_context()` which starts another. They may conflict on port or profile lock.
- **`winsound`** — Windows-only module. Bot will crash on Linux/macOS.
- **No lint, no typecheck** configured in this repo.
- **All selectors are hardcoded at the top of `bot.py`** (lines ~84–93). Edit `bot.py` directly.
- **Chat logs** written to `chat_logs/` relative to CWD. Run from the repo root to get `AGM/chat_logs/`. The folder is gitignored; `success/` subfolder + `summary.csv` are created on demand.
- **`DEBUG = True`** hardcoded in bot.py (line 14) — all `[DEBUG]` output goes to stdout.
- **Response time on timeout is always 0** — `wait_for_partner_msg` returns `(None, count, 0)` on timeout, not the actual elapsed time.

## Testing

`test_bot.py` — 650+ unit tests on pure logic (patterns, filters, helpers). Run:

```powershell
$env:PYTHONIOENCODING='utf-8'; python test_bot.py
```

**All tests MUST pass before and after any change to bot.py.** If a test fails after your change — revert.

**Every new function/pattern added to bot.py MUST have a corresponding test** in `test_bot.py` covering its logic (edge cases, false positives, correct matching).

## Workflow Protocol

1. **Git commit before changes** — always commit current working state before editing
2. **Targeted changes only** — make exactly what's requested, don't touch working parts
3. **Run tests after changes** — `python test_bot.py`, all must pass
4. **Changelog** — record changes in `CHANGELOG.md`
5. **Don't rewrite** — edit existing code, don't rewrite functions from scratch
