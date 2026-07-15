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

## Gotchas

- **Selectors duplicated**: `bot.py:11-20` hardcodes its own CSS selectors. `config.py:28-37` has a `SELECTORS` dict — but only the unused OOP modules reference it. If updating selectors, edit `bot.py` directly.
- **ALL chrome.exe killed**: `start-chrome.bat` runs `taskkill /F /IM chrome.exe` — closes every Chrome window.
- **Two Chrome instances**: The bat starts Chrome on port 9222; `bot.py` calls `launch_persistent_context` which starts its own. Running both may conflict on port or profile lock.
- **QWEN.md and CHat/README.md are aspirational** — they describe architecture (state machine, brain/observer/executor modules, ChatLLM/) that doesn't exist in the running code.
