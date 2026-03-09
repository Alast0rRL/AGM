# AGM Project Context

## Project Overview

AGM is a collection of AI-powered chat automation tools consisting of two main subprojects:

### 1. CHat (Amor-Bot v1.0)
A dating chat automator for **Nekto.me** that uses a local LLM (Qwen 2.5 7B via Ollama) to conduct conversations. The bot simulates human-like behavior with typing delays, anti-detection features, and a state machine for conversation flow.

**Key Features:**
- **Observer Module**: Monitors page state, detects messages every 500ms
- **Brain Module**: LLM integration with context management and prompt engineering
- **Executor Module**: Human-like typing with randomized delays
- **State Machine**: IDLE → HOOK → ENGAGE → CONVERSION → RESET
- **Anti-Detection**: Random delays, remote debugging, human-like input patterns

### 2. ChatLLM
A multi-persona Telegram bot framework using OpenRouter/OpenAI APIs with persistent memory via SQLite.

**Key Features:**
- Multiple bot personas (Bitsy, Aether-7, Kite, Huilan)
- SQLite-based conversation history
- OpenRouter API integration for various LLM models
- Platform-specific formatting (Telegram/Discord)

---

## Directory Structure

```
AGM/
├── CHat/                    # Nekto.me automation bot
│   ├── bot.py              # Main orchestrator with state machine
│   ├── observer.py         # Page monitoring module
│   ├── brain.py            # LLM integration module
│   ├── executor.py         # Input simulation module
│   ├── config.py           # Configuration settings
│   ├── requirements.txt    # Python dependencies
│   ├── .env.example        # Environment template
│   ├── start-chrome.bat    # Chrome launch script
│   └── README.md
│
├── ChatLLM/                 # Telegram bot framework
│   ├── tg_bot.py           # Telegram bot main handler
│   ├── ai_client.py        # OpenRouter/OpenAI client
│   ├── bot_profile.py      # Bot persona definitions
│   ├── memory.py           # SQLite memory manager
│   ├── system_prompts.md   # System prompt templates
│   ├── .env                # Environment configuration
│   └── README.md
│
├── page_debug.html         # Saved page HTML for debugging
└── QWEN.md                 # This file
```

---

## Building and Running

### CHat (Nekto.me Bot)

**Prerequisites:**
- Python 3.10+
- Google Chrome
- Ollama with Qwen 2.5 7B model

**Setup:**
```bash
cd CHat
pip install -r requirements.txt
playwright install chromium
ollama pull qwen2.5:7b
```

**Configuration:**
```bash
# Copy and edit .env
copy .env.example .env
```

**Start Chrome with remote debugging:**
```bash
# Windows
.\start-chrome.bat
# Or manually:
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\YourName\AppData\Local\Google\Chrome\User Data"
```

**Run the bot:**
```bash
python bot.py
```

### ChatLLM (Telegram Bot)

**Prerequisites:**
- Python 3.10+
- Telegram Bot Token
- OpenRouter or OpenAI API key

**Setup:**
```bash
cd ChatLLM
pip install openai python-dotenv aiogram
```

**Configuration:**
Edit `.env` with your API keys and bot settings.

**Run the bot:**
```bash
python tg_bot.py
```

---

## Development Conventions

### Code Style
- Python with type hints where applicable
- Async/await pattern for I/O operations
- Modular architecture (observer, brain, executor pattern)

### Configuration
- Environment variables via `.env` files
- `python-dotenv` for loading configuration
- Sensible defaults in config modules

### Testing Practices
- Manual testing via CLI execution
- Test scripts included (e.g., `test_personas.py`)

### Key Patterns
- **State Machine**: Bot transitions through IDLE → HOOK → ENGAGE → CONVERSION → RESET
- **Module Separation**: Clear separation of concerns (observation, reasoning, execution)
- **Anti-Detection**: Randomized delays, human-like typing patterns

---

## Key Configuration Options

### CHat Environment Variables
| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_URL` | Ollama API endpoint | `http://localhost:11434/api/generate` |
| `LLM_MODEL` | Model name | `qwen2.5:7b` |
| `TELEGRAM_USERNAME` | Telegram username for conversion | `""` |
| `REMOTE_DEBUGGING_PORT` | Chrome debugging port | `9222` |
| `SCAN_INTERVAL` | Page scan interval (ms) | `500` |
| `SILENCE_TIMEOUT` | Silence timeout (ms) | `60000` |

### ChatLLM Environment Variables
| Variable | Description |
|----------|-------------|
| `OPENROUTER_API_KEY` | OpenRouter API key |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `AI_MODEL` | Model identifier (e.g., `openai/gpt-4o-mini`) |
| `CURRENT_PERSONA` | Active bot persona |

---

## Bot Personas (ChatLLM)

| Persona | Description |
|---------|-------------|
| **Bitsy** | Energetic digital sprite, IT metaphors |
| **Aether-7** | Digital chronicler, polite and knowledgeable |
| **Kite** | Sarcastic fixer, concise and results-focused |
| **Huilan** | MMA champion, gruff and direct (default) |

---

## Troubleshooting

**CHat - Cannot connect to Chrome:**
- Ensure Chrome is running with `--remote-debugging-port=9222`
- Close all Chrome instances and restart with the flag

**CHat - LLM not responding:**
- Check Ollama is running: `ollama list`
- Verify model: `ollama pull qwen2.5:7b`

**ChatLLM - API errors:**
- Verify API keys in `.env`
- Check OpenRouter/OpenAI service status
