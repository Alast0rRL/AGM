# Amor-Bot v1.0

Dating AI Automator for Nekto.me using local LLM (Qwen 2.5 7B).

## Requirements

- Python 3.10+
- Google Chrome
- Ollama with Qwen 2.5 7B model

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
playwright install chromium
```

2. Install and configure Ollama:
```bash
# Download Ollama from https://ollama.ai
ollama pull qwen2.5:7b
```

3. Configure environment:
```bash
# Copy .env.example to .env
copy .env.example .env

# Edit .env with your settings:
# - TELEGRAM_USERNAME=your_username
# - USER_DATA_DIR=your_chrome_profile_path
```

4. Start Chrome with remote debugging:
```bash
# Windows
"C:\Program Files\Google\Chrome\Application\chrome.exe" --remote-debugging-port=9222 --user-data-dir="C:\Users\YourName\AppData\Local\Google\Chrome\User Data"

# Or use the included script
.\start-chrome.bat
```

5. Run the bot:
```bash
python bot.py
```

## Project Structure

```
CHat/
├── bot.py          # Main orchestrator
├── observer.py     # Page monitoring module
├── brain.py        # LLM integration module
├── executor.py     # Input simulation module
├── config.py       # Configuration settings
├── requirements.txt
├── .env.example
└── README.md
```

## Features

- **Observer Module**: Monitors page state, detects messages every 500ms
- **Brain Module**: LLM integration with context management and prompt engineering
- **Executor Module**: Human-like typing with randomized delays
- **State Machine**: IDLE → HOOK → ENGAGE → CONVERSION → RESET
- **Anti-Detection**: Random delays, remote debugging, human-like input patterns

## Configuration

Edit `.env` file:

| Variable | Description | Default |
|----------|-------------|---------|
| `LLM_API_URL` | Ollama API endpoint | `http://localhost:11434/api/generate` |
| `LLM_MODEL` | Model name | `qwen2.5:7b` |
| `TELEGRAM_USERNAME` | Your Telegram username | `""` |
| `REMOTE_DEBUGGING_PORT` | Chrome debugging port | `9222` |
| `USER_DATA_DIR` | Chrome profile path | `""` |
| `SCAN_INTERVAL` | Page scan interval (ms) | `500` |
| `TYPING_DELAY_MIN` | Min typing delay (ms) | `50` |
| `TYPING_DELAY_MAX` | Max typing delay (ms) | `150` |
| `SILENCE_TIMEOUT` | Silence timeout (ms) | `60000` |

## Bot Behavior

### Style
- Lowercase only
- No trailing periods
- Short messages (3-6 words average)
- Minimal emojis (1 per 3 messages)

### Flow
1. **IDLE**: Wait for chat opportunity
2. **HOOK**: Send random opener from predefined list
3. **ENGAGE**: Maintain conversation, ask questions
4. **CONVERSION**: Suggest Telegram when sympathy index is high
5. **RESET**: Clear context on chat end, return to IDLE

### Quick Responses
- "М или Ж" → "м" (instant, no LLM call)
- Aggression detection → Auto-leave chat

## Troubleshooting

**Cannot connect to Chrome:**
- Make sure Chrome is running with `--remote-debugging-port=9222`
- Close all Chrome instances and restart with the flag

**LLM not responding:**
- Check Ollama is running: `ollama list`
- Verify model is downloaded: `ollama pull qwen2.5:7b`

**Selectors not working:**
- Nekto.me may have updated their HTML
- Edit `SELECTORS` in `config.py` to match current structure

## License

MIT
