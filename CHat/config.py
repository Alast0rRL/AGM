"""Configuration settings for Amor-Bot v1.0"""

import os
from dotenv import load_dotenv

load_dotenv()

# LLM Backend
LLM_API_URL = os.getenv("LLM_API_URL", "http://localhost:11434/api/generate")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5:7b")

# Bot Configuration
TELEGRAM_USERNAME = os.getenv("TELEGRAM_USERNAME", "")
REMOTE_DEBUGGING_PORT = int(os.getenv("REMOTE_DEBUGGING_PORT", "9222"))
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "")

# Timing (milliseconds)
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL", "500"))
TYPING_DELAY_MIN = int(os.getenv("TYPING_DELAY_MIN", "50"))
TYPING_DELAY_MAX = int(os.getenv("TYPING_DELAY_MAX", "150"))
THINKING_DELAY_BASE = int(os.getenv("THINKING_DELAY_BASE", "1000"))
SILENCE_TIMEOUT = int(os.getenv("SILENCE_TIMEOUT", "60000"))

# Anti-detection
DELAY_VARIANCE = float(os.getenv("DELAY_VARIANCE", "0.20"))

# Nekto.me Selectors
SELECTORS = {
    "messages_container": ".window_chat_block, .messages-container, .chat-messages",
    "incoming_msg": ".mess_block.nekto",
    "outgoing_msg": ".mess_block.self",
    "input_field": ".emojionearea-editor[contenteditable='true'], #message_textarea, textarea[data-type='input']",
    "send_button": ".send_btn_circle, .sendMessageBtn, #sendMessageBtn, button.send",
    "new_chat_button": ".talk_over_button, #searchCompanyBtn, .search-btn, button:has-text('Начать чат'), button:has-text('Начать')",
    "chat_ended_indicator": ".status-end.talk_over, .chat-ended, .dialog-closed",
}

# Openers (best performing first messages)
OPENERS = [
    "привет, как настроение?",
    "хай, чем занимаешься?",
    "приветик, скучно стало - решил зайти сюда",
    "ку, есть кто живой?",
    "привет, расскажи что-нибудь о себе",
]

# Quick responses for common patterns
QUICK_RESPONSES = {
    "м или ж": "м",
    "м/ж": "м",
    "пол": "м",
    "возраст": "25",
    "как зовут": "аноним",
}

# Conversion triggers (keywords that indicate readiness to move to Telegram)
CONVERSION_KEYWORDS = [
    "классно",
    "интересно",
    "понравилось",
    "круто",
    "здорово",
    "класс",
    "супер",
]

# Aggression detection
AGGRESSION_KEYWORDS = [
    "иди нах",
    "пошел нах",
    "заткнись",
    "тупой",
    "дегенерат",
    "бот",
]

# Positive sentiment for sympathy calculation
POSITIVE_SENTIMENT = [
    "классно",
    "интересно",
    "понравилось",
    "круто",
    "здорово",
    "класс",
    "супер",
    "мило",
    "умный",
    "весело",
    "приятно",
    "рада",
    "рад",
    "обнимаю",
    "целую",
    "скучаю",
    "хочу",
    "давай",
    "конечно",
    "обязательно",
]

# Negative sentiment
NEGATIVE_SENTIMENT = [
    "скучно",
    "не интересно",
    "отстань",
    "пока",
    "достал",
    "надоел",
    "фу",
    "мерзко",
    "противно",
]
