# AGM — Agent Reference

## What this repo is

A Nekto.me dating chat automator (`CHat/`). Uses Playwright (Python) to launch Chrome and automate Russian chat conversation. **Windows-only** (`winsound`, `.bat`).

## Critical: LLM is dead code

`bot.py` does NOT import `brain.py` / `observer.py` / `executor.py`. The running bot is **fully hardcoded** — sends `привет`, asks `сколько лет`, beeps for ages 17-19, then logs messages. The Ollama/LLM integration described in `CHat/README.md` and `.env.example` does **not exist in the running code**. Treat the three OOP modules as draft/legacy.

## Project structure

```
AGM/
  CHat/                     # Active subproject
    bot.py                  # Entrypoint — monolithic hardcoded loop
    config.py               # Env-based config; only USER_DATA_DIR & REMOTE_DEBUGGING_PORT used by bot.py
    observer.py             # Unused OOP module (draft)
    brain.py                # Unused OOP module (draft)
    executor.py             # Unused OOP module (draft)
    .env.example            # Template — copy to .env
    start-chrome.bat        # Kills ALL chrome.exe, launches on port 9222
  QWEN.md                   # Misleading — references non-existent ChatLLM/ subproject
  README.md                 # Nearly empty
  chat_logs/                # Logs when running bot.py from repo root
```

## Setup & run

```powershell
cd CHat
pip install -r requirements.txt   # playwright, httpx, python-dotenv
playwright install chromium
copy .env.example .env            # edit USER_DATA_DIR to a Chrome profile path
.\start-chrome.bat                # kills ALL chrome.exe, launches Chrome on port 9222
python bot.py
```

- `ollama pull qwen2.5:7b` is **unnecessary** — LLM code is dead.
- `start-chrome.bat` launches its own Chrome instance, but `bot.py` also calls `launch_persistent_context` which starts **another**. Running both may conflict on port or profile lock.
- `.env` in `CHat/` must set `USER_DATA_DIR` to a writable Chrome profile path.
- Chat logs land relative to CWD (`chat_logs/` directory). From `CHat/`, that's `CHat/chat_logs/`.

## No tests, no lint, no typecheck

No test runners, linters, or type checkers configured.

## Bot flow (bot.py)

The bot runs a loop: find partner → send "привет" → wait for reply → pattern-match → ask age → filter 17-19 → enter wait mode.

**Pattern matching** (checked in order on the first reply):
- `is_age_question` — partner asks bot's age → answer "19"
- `is_name_ask` — partner asks name → "Максим, тебя?"
- `is_self_introduction` — partner introduces themselves → "Максим, тебя?"
- `is_nice_to_meet` — "приятно познакомиться" → "взаимно"
- `is_from_question` — "откуда" → "Уже в гости собралась"
- `is_and_you` — "а тебе?" → "Тож"
- `is_how_are_you` — "как дела" → "норм, ты как?"
- Fallback: ask "сколько лет"

**Age filtering**: `target_ages = [17, 18, 19]`. Ages outside this range → skip/end chat. Underage (<17) detected both by `is_underage()` pattern list AND numeric check on leading digits.

**Skip conditions** (checked before pattern matching): `is_ukrainian`, `is_muslim`, `is_dismissive`, `is_underage`.

**`enter_wait_mode`**: After age is confirmed 17-19, loops waiting for name/from/age questions from partner, answering them. Runs for 60 iterations (1s each).

**Key pattern lists** (all in bot.py):
- `AGE_ASK_PATTERNS` — questions about age (includes misspellings: "сколика", "сколко", "скок", etc.)
- `AND_YOU_PATTERNS` — "а тебе?", "тебе", "тебя", etc.
- `DISMISSIVE_PATTERNS` — rude/dismissive phrases → skip chat
- `UNDERAGE_PATTERNS` — age indicators <17
- `HOW_ARE_YOU_PATTERNS` — "как дела", "как ты", etc.
- `WHAT_ARE_YOU_DOING_PATTERNS` — "что делаешь", etc.

## Gotchas

- **Selectors hardcoded in bot.py**: `config.py:28-37` has a `SELECTORS` dict but only the unused OOP modules reference it. If updating selectors, edit `bot.py` directly.
- **ALL chrome.exe killed**: `start-chrome.bat` runs `taskkill /F /IM chrome.exe` — closes every Chrome window.
- **Two Chrome instances**: The bat starts Chrome on port 9222; `bot.py` calls `launch_persistent_context` which starts its own. Running both may conflict on port or profile lock.
- **QWEN.md and CHat/README.md are aspirational** — they describe architecture (state machine, brain/observer/executor modules, ChatLLM/) that doesn't exist in the running code.
- **`wait_for_partner_msg` returns hardcoded 0 for response_time on timeout/early-exit** — log shows `time=0.0s` even after waiting full timeout. The actual elapsed time is not captured in the return value.
- **Russian text patterns**: Many patterns are substring-based (`if p in t`). Adding new patterns requires care — "тебе" without "?" must be listed separately from "тебе?".
