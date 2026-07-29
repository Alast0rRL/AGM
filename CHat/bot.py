import asyncio
import os
import re
import random
import time
import winsound
import threading
import queue
from dataclasses import dataclass, field
from datetime import datetime
from playwright.async_api import async_playwright
from config import USER_DATA_DIR, REMOTE_DEBUGGING_PORT

DEBUG = True

def log(msg):
    if DEBUG:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"  [{ts}] [DEBUG] {msg}", flush=True)

# --- TTS (озвучка сообщений) ---
_tts_queue = queue.Queue()
_tts_ready = False
_tts_enabled = True
_tts_exposed = False
_TTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voices")
_TTS_FEMALE_MODEL = os.path.join(_TTS_DIR, "ru_RU-irina-medium.onnx")
_TTS_MALE_MODEL = os.path.join(_TTS_DIR, "ru_RU-ruslan-medium.onnx")

def _tts_worker():
    global _tts_ready
    import numpy as np

    print("  [TTS] worker starting...", flush=True)

    try:
        from piper import PiperVoice, SynthesisConfig
        print("  [TTS] piper import OK", flush=True)
    except Exception as e:
        print(f"  [TTS] piper import failed: {e}", flush=True)
        return

    try:
        female_voice = PiperVoice.load(_TTS_FEMALE_MODEL)
        male_voice = PiperVoice.load(_TTS_MALE_MODEL)
        _syn_config = SynthesisConfig(length_scale=0.85)
        print("  [TTS] voices loaded", flush=True)
    except Exception as e:
        print(f"  [TTS] voice load failed: {e}", flush=True)
        return

    try:
        import sounddevice as sd
        print("  [TTS] sounddevice OK", flush=True)
    except Exception as e:
        print(f"  [TTS] sounddevice failed: {e}", flush=True)
        return

    _tts_ready = True
    print("  [TTS] ready, waiting for messages...", flush=True)

    while True:
        text, female = _tts_queue.get()
        voice = female_voice if female else male_voice
        try:
            all_audio = []
            sample_rate = None
            for chunk in voice.synthesize(text, syn_config=_syn_config):
                if sample_rate is None:
                    sample_rate = chunk.sample_rate
                all_audio.append(np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16))
            if all_audio and sample_rate:
                audio = np.concatenate(all_audio).astype(np.float32) / 32768.0
                stream = sd.Stream(samplerate=sample_rate, channels=1, dtype='float32')
                stream.start()
                stream.write(audio.reshape(-1, 1))
                stream.stop()
                stream.close()

        except Exception as e:
            print(f"  [TTS] speak error: {type(e).__name__}: {e}", flush=True)
        _tts_queue.task_done()

async def speak(text, female=True):
    global _tts_enabled
    if not _tts_enabled:
        return
    _tts_queue.put((text, female))

def _set_tts_enabled(val: bool):
    global _tts_enabled
    _tts_enabled = val

async def setup_tts_toggle(page):
    """Экспортирует функцию переключения TTS в страницу."""
    global _tts_exposed
    if not _tts_exposed:
        await page.expose_function("_py_set_tts", _set_tts_enabled)
        _tts_exposed = True

async def _inject_tts_panel(page):
    """Инжектит панель TTS в DOM + MutationObserver для авто-восстановления."""
    try:
        has = await page.evaluate("!!document.getElementById('tts-toggle-panel')")
        if has:
            return
        body_ok = await page.evaluate("!!document.body")
        log(f"[TTS toggle] inject: body={body_ok}")
        if not body_ok:
            return
        await page.evaluate("""
(function(){
var ID = 'tts-toggle-panel';
var ON = '&#x1F50A;';
var OFF = '&#x1F507;';
function makePanel(){
    var el = document.getElementById(ID);
    if (el) return el;
    var p = document.createElement('div');
    p.id = ID;
    p.dataset.enabled = 'true';
    p.innerHTML = '<span id="tts-icon">'+ON+'</span>';
    p.style.cssText = 'position:fixed;top:10px;right:10px;z-index:99999;background:#222;color:#fff;padding:8px 12px;border-radius:8px;cursor:pointer;font-size:20px;user-select:none;font-family:Arial;box-shadow:0 2px 8px rgba(0,0,0,0.3);line-height:1';
    p.onclick = function(){
        var nv = p.dataset.enabled !== 'false' ? false : true;
        p.dataset.enabled = nv;
        var icon = document.getElementById('tts-icon');
        if (icon) icon.innerHTML = nv ? ON : OFF;
        if (window._py_set_tts) window._py_set_tts(nv);
    };
    document.body.appendChild(p);
    return p;
}
makePanel();
if (!window._ttsObserver) {
    window._ttsObserver = new MutationObserver(function(){
        if (!document.getElementById(ID)) makePanel();
    });
    window._ttsObserver.observe(document.documentElement, { childList: true, subtree: true });
}
})();
""")
        log("[TTS toggle] injected OK")
    except Exception as e:
        log(f"[TTS toggle] inject FAIL: {e}")

# Селекторы (настроены под текущую верстку Nekto.me)
START_BUTTON = "#searchCompanyBtn"
ACCEPT_RULES = ".swal2-confirm"
INPUT_FIELD = ".emojionearea-editor"
# Селектор для текста сообщения - ищем внутри .window_chat_dialog_text
MESSAGES = ".window_chat_dialog_text"
# Кнопка завершения чата - ищем по тексту или классам
STOP_BUTTON = "button:has-text('Завершить'), .btn-stop, .btn-quit, .exit_but, .btn-my2, button.talk_over_button:has-text('Завершить')"
CONFIRM_STOP = ".swal2-confirm"
# Кнопка "Начать новый чат" - появляется когда чат завершен
NEW_CHAT_BUTTON = "button:has-text('Начать новый чат')"

async def human_type(page, text):
    """Печатает текст быстро (имитация человека, но без лишних задержек)"""
    el = await page.query_selector(INPUT_FIELD)
    if not el:
        return False
    cls = await el.evaluate("el => el.closest('.emojionearea')?.className || ''")
    if 'disable' in cls:
        return False
    await page.click(INPUT_FIELD)
    await page.type(INPUT_FIELD, text, delay=random.randint(10, 30))
    await page.keyboard.press("Enter")
    print(f"Отправлено: {text}")
    await speak(text, female=False)
    return True

async def get_msg_role(page, msg_element):
    """Определяет, отправлено ли сообщение ботом (self) или собеседником"""
    return await msg_element.evaluate("""el => {
        const block = el.closest('.mess_block');
        if (!block) return 'unknown';
        if (block.classList.contains('self')) return 'self';
        if (block.classList.contains('nekto')) return 'nekto';
        return 'unknown';
    }""")

async def hover_msg(page, element):
    try:
        await element.hover()
        await asyncio.sleep(0.05)
    except:
        pass

async def wait_for_partner_msg(page, last_count, all_messages: list = None, timeout: float = None):
    """Ждет нового сообщения от собеседника с опциональным таймаутом"""
    import time
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > 2:
            input_field = await page.query_selector(INPUT_FIELD)
            input_visible = False
            try:
                input_visible = input_field and await input_field.is_visible()
            except:
                pass
            new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
            new_chat_visible = False
            try:
                new_chat_visible = new_chat_btn and await new_chat_btn.is_visible()
            except:
                pass
            if not input_visible or new_chat_visible:
                # Повторная проверка через 1 сек — поле могло быть временно скрыто
                await asyncio.sleep(1)
                input_field2 = await page.query_selector(INPUT_FIELD)
                input_visible2 = False
                try:
                    input_visible2 = input_field2 and await input_field2.is_visible()
                except:
                    pass
                new_chat_btn2 = await page.query_selector(NEW_CHAT_BUTTON)
                new_chat_visible2 = False
                try:
                    new_chat_visible2 = new_chat_btn2 and await new_chat_btn2.is_visible()
                except:
                    pass
                if not input_visible2 or new_chat_visible2:
                    return None, last_count, 0
        
        current_msgs = await page.query_selector_all(MESSAGES)
        if len(current_msgs) > last_count:
            await hover_msg(page, current_msgs[-1])
            for i in range(last_count, len(current_msgs)):
                role = await get_msg_role(page, current_msgs[i])
                text = await current_msgs[i].inner_text()
                if role == 'self':
                    if all_messages is not None:
                        all_messages.append({"role": "self", "content": text})
                    last_count = i + 1
                    continue
                log(f"  [wait_for_partner] got: '{text}' (role={role})")
                print(f"Собеседник: {text}")
                await speak(text, female=True)
                if all_messages is not None:
                    all_messages.append({"role": "other", "content": text})
                response_time = time.time() - start_time
                return text, i + 1, response_time
            last_count = len(current_msgs)
        
        if timeout is not None and (time.time() - start_time) > timeout:
            return None, last_count, 0
        
        await asyncio.sleep(0.2)

async def reset_for_new_chat(page):
    """Приводит страницу в состояние готовности к новому чату."""
    await asyncio.sleep(1)
    try:
        new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
        if new_chat_btn and await new_chat_btn.is_visible():
            return
    except:
        pass
    try:
        await page.goto("https://nekto.me/chat/#/", timeout=15000)
    except:
        pass
    await asyncio.sleep(2)

async def start_new_chat(page):
    """Начинает новый чат или продолжает активный"""
    print("\n--- Запуск нового цикла ---")
    
    # Проверяем, есть ли уже активный чат (поле ввода видимо, кнопка нового чата нет)
    try:
        existing_input = await page.query_selector(INPUT_FIELD)
        new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
        btn_visible = False
        if new_chat_btn:
            btn_visible = await new_chat_btn.is_visible()
        if existing_input and await existing_input.is_visible() and not btn_visible:
            msgs = await page.query_selector_all(MESSAGES)
            if not msgs:
                return 0
            # Есть сообщения — возможно залипло, форсируем новый чат
            await reset_for_new_chat(page)
    except:
        pass
    
    # Пробуем нажать "Начать чат" если чат завершен
    try:
        new_chat_btn = await page.wait_for_selector(NEW_CHAT_BUTTON, timeout=2000)
        if new_chat_btn:
            await new_chat_btn.click()
            await asyncio.sleep(1)
    except:
        # Если кнопки нет, идем на главную и ищем основную кнопку
        try:
            await page.goto("https://nekto.me/chat/#/", timeout=15000)
        except:
            pass
        await asyncio.sleep(2)
        try:
            await page.wait_for_selector(START_BUTTON, timeout=10000)
            await page.click(START_BUTTON)
        except:
            try:
                await page.reload(timeout=15000)
            except:
                pass
            await asyncio.sleep(3)
            try:
                await page.wait_for_selector(START_BUTTON, timeout=20000)
                await page.click(START_BUTTON)
            except:
                raise
    
    # Принять правила (если выскочат)
    try:
        await page.wait_for_selector(ACCEPT_RULES, timeout=2000)
        await page.click(ACCEPT_RULES)
    except:
        pass
    
    # Ждем появления поля ввода (собеседник найден)
    try:
        await page.wait_for_selector(INPUT_FIELD, timeout=300000)
        print("Собеседник найден!")
    except Exception as e:
        print(f"Ошибка поиска собеседника: {e}")
        raise
    
    msgs = await page.query_selector_all(MESSAGES)
    return len(msgs)

async def end_chat(page):
    """Завершает текущий чат"""
    # 1. Ищем кнопку "Завершить" по всем известным селекторам
    stop = None
    for selector in STOP_BUTTON.split(", "):
        try:
            stop = await page.wait_for_selector(selector, timeout=2000)
            if stop:
                await stop.click()
                break
        except:
            continue

    if not stop:
        return

    # 2. Ждём и нажимаем подтверждение в диалоговом окне
    await asyncio.sleep(1)
    CONFIRM_SELECTORS = [CONFIRM_STOP, ".swal2-confirm.swal2-styled", "button:has-text('OK')", "button:has-text('Да')", ".swal2-actions button"]
    for selector in CONFIRM_SELECTORS:
        try:
            confirm = await page.wait_for_selector(selector, timeout=3000)
            if confirm and await confirm.is_visible():
                await confirm.click()
                await asyncio.sleep(1)
                return
        except:
            continue

async def save_chat_log(messages: list, age: str):
    """Сохраняет лог чата в файл"""
    import os
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Создаем папку если не существует
    log_dir = "chat_logs"
    os.makedirs(log_dir, exist_ok=True)
    
    filename = f"{log_dir}/chat_{timestamp}_age{age}.txt"
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(f"=== Чат от {timestamp} ===\n")
        f.write(f"Возраст собеседника: {age}\n")
        f.write(f"Всего сообщений: {len(messages)}\n\n")
        
        for msg in messages:
            role = "Я" if msg["role"] == "own" else "Собеседник"
            f.write(f"[{role}] {msg['content']}\n")
    
    print(f"Лог: {filename}")
    return filename

AGE_ASK_PATTERNS = [
    # Явные вопросы со "сколько"
    "сколько тебе", "а тебе сколько", "тебе сколько",
    "сколько тебя", "сколько лет",
    "вам сколько",
    # С "возраст"
    "твой возраст",
    # Сленг
    "скока", "скоко", "сколька", "сколко", "скок",
    "скока тебе", "скока лет", "скок лет",
    # Славянские формы
    "самой", "самому",
    # Опечатки
    "сколика", "сколик",
    "скилко", "скалко", "колко",
    "а тибе", "а тибя",
    "тибе", "тибя",
    "теюе", "а теюе", "теье", "а теье",
    "атебе",
]

NAME_ASK_PATTERNS = [
    "как тебя зовут", "как зовут", "как звать",
    "а зовут как", "зовут как",
    "твое имя", "твоё имя", "имя как",
    "а тебя", "представься",
    "как тебя", "а как тебя",
    "имя?", "имя ?", "как называть",
    "тебя?", "тебя ?", "а тебя?", "а тебя ?",
    "как вас зовут", "вас зовут",
    "как вас", "а как вас",
    "вас?", "вас ?", "а вас?", "а вас ?",
]

ZOVUT_PATTERNS = ["зовут?"]


def is_self_introduction(text: str) -> bool:
    """Проверяет, представляется ли собеседник ('Я Света', 'Привет Я Эльвина 19')"""
    if not text:
        return False
    t = text.strip()
    tl = t.lower()
    if "меня зовут" in tl or "зови меня" in tl:
        return True
    words = tl.split()
    orig_words = t.split()
    for i, w in enumerate(words):
        if w == "я" and i + 1 < len(words) and words[i + 1][0].isalpha():
            next_word = words[i + 1]
            is_verb = bool(re.search(r'(ую|уя|аю|ая|юсь|усь|юет|ует|ает|ает|али|ило|ила|ули)$', next_word))
            if is_verb:
                continue
            rest = " ".join(words[i+1:])
            has_digit = any(c.isdigit() for c in rest)
            has_name = any(ch.isupper() for w in orig_words[i+1:] for ch in w if ch.isalpha())
            if has_digit or has_name:
                return True
    greeting_re = re.compile(r'^(привет|хай|хей|здарова|салам|йо)\b', re.IGNORECASE)
    m = greeting_re.match(tl)
    if m:
        after_greeting = tl[m.end():].strip()
        after_greeting_orig = t[m.end():].strip()
        rest_words = after_greeting.split()
        rest_orig = after_greeting_orig.split()
        if rest_words:
            first = rest_words[0].lstrip('.!?,;:')
            first_orig = rest_orig[0].lstrip('.!?,;:')
            if first and first[0].isalpha() and len(first) > 1:
                has_upper = any(c.isupper() for c in first_orig if c.isalpha())
                has_digit = any(c.isdigit() for c in " ".join(rest_words))
                if has_upper or has_digit:
                    return True

    if len(t.split()) >= 2:
        first_orig = orig_words[0]
        first_lower = words[0]
        if (first_orig[0].isupper() and first_lower.isalpha()
                and first_lower not in _GREETINGS and first_lower not in _NOT_NAMES):
            if any(c.isdigit() for c in " ".join(words[1:])):
                return True
    return False

FROM_ASK_PATTERNS = [
    "откуда", "где живешь", "где ты живешь",
    "с какого города", "из какого города", "какого ты города",
    "в каком городе", "какой город", "откуда ты",
]

NICE_TO_MEET_PATTERNS = [
    "приятно познакомиться", "приятно знакомиться",
    "приятно познакомится", "приятно знакомится",
    "рада знакомству", "рад знакомству",
    "приятно",
]

AND_YOU_PATTERNS = [
    "а ты", "а а ты", "а ты как", "а ты откуда",
    "а у тебя", "а у а ты",
    "а ты?", "а ты а",
    "а тебе", "а те",
    "а вам", "а вас",
    "тебе?", "тебе ?", "тебя?", "тебя ?",
    "вам?", "вам ?", "вас?", "вас ?",
    "те?", "те ?",
]

_SHORT_AND_YOU = {"те", "теб", "и те", "тебе"}

WHAT_ARE_YOU_DOING_PATTERNS = [
    "что делаешь", "чем занят", "чем занимаешься",
    "что сейчас делаешь", "чем шумишь",
]

LOOKING_FOR_PATTERNS = [
    "что ищешь", "кого ищешь",
]

HOW_ARE_YOU_PATTERNS = [
    "как дела", "как у дела", "как твои дела",
    "как сам", "как сама", "как жизнь",
    "что нового", "как поживаешь",
    "как оно", "как там",
]

CONFIRMATION_PATTERNS = ["да", "верно", "точно", "правда", "ага"]

COMPLIMENT_PATTERNS = [
    "красивое имя", "крутое имя", "хорошее имя",
    "прикольное имя", "милое имя", "стрange имя",
    "какое имя", "имя крутое", "имя красивое",
    "классное имя", "интересное имя",
]

RUSSIAN_CONFIRM_PATTERNS = [
    "да", "ага",
    "да, русская", "да русская",
    "конечно", "да, конечно", "да конечно",
]

RUSSIAN_DENY_PATTERNS = [
    "нет", "неа",
    "не русская", "не рус",
    "татарка", "армянка", "чувачка", "азербайджанка",
    "казашка", "узбечка",
]

TG_CONTINUE_PATTERNS = [
    "в тг", "в телеграм", "телеграм",
    "тг", "тг?", "тг.",
    "ссылк", "ссылку", "ссылкой",
    "свой тг", "свой телеграм",
    "напиши в тг", "напиши в телеграм",
    "продолжить в тг", "продолжим в тг",
    "перейдём в тг", "перейдем в тг",
    "скинь тг", "скинь ссылк",
    "дай тг", "дашь тг",
]

def is_confirmation_question(text: str) -> bool:
    t = text.lower().strip()
    if not any(p in t for p in ["а ты"]):
        return False
    # Strip punctuation from words for matching
    words = [w.strip('?!.,;:') for w in t.split()]
    if words and words[-1] in CONFIRMATION_PATTERNS:
        return True
    # Check for confirmation words as separate words after "а ты"
    after_atyu = t.split("а ты", 1)
    if len(after_atyu) > 1:
        after_words = [w.strip('?!.,;:') for w in after_atyu[1].split()]
        if any(p in after_words for p in CONFIRMATION_PATTERNS):
            return True
    return False

def _name_already_sent(chat_messages):
    for msg in chat_messages:
        if "максим" in msg.get("content", "").lower():
            return True
    return False

def _already_sent_19(chat_messages):
    for msg in chat_messages:
        if msg.get("role") in ("own", "self") and msg.get("content", "").strip() == "19":
            return True
    return False

_GREETINGS = {
    "привет", "приветик", "здравствуй", "здравствуйте",
    "хай", "хей", "здарова", "салам", "йо",
}

_NOT_NAMES = {
    "понятно", "круто", "ладно", "точно", "правда", "серьёзно", "серьезно",
    "интересно", "странно", "жаль", "класс", "супер", "오키", "норм",
    "прикольно", "забавно", "обидно", "жаль", "конечно", "разумеется",
    "возможно", "наверное", "пожалуй", "думаю", "ага", "ну", "вот",
    "кстати", "вообще", "прям", "типа", "короче", "слушай", "кстати",
    "пожалуйста", "спасибо", "пожалуй", "извини", "прости", "чё", "чего",
    "ничего", "всё", "все", "окей", "ок", "йес", "нет", "да",
    "нормас", "норма", "нормально", "нормально)",
     "ростов", "те", "ааа", "аааа", "ааааа", "хммм", "ммм", "угу", "аа", "уу",
    "тебе", "лет",
}

def _partner_name_received(chat_messages):
    for msg in chat_messages:
        if msg["role"] != "other":
            continue
        content = msg["content"].strip()
        if is_self_introduction(content):
            return True
        words = content.split()
        if len(words) == 1 and words[0].isalpha():
            if words[0].lower() not in _GREETINGS and words[0].lower() not in _NOT_NAMES:
                return True
    return False

def _extract_name_first_word(resp: str) -> str | None:
    """Извлекает имя из первого слова с заглавной (например 'Лена, приятно познакомиться' -> 'Лена')."""
    if not resp:
        return None
    words = resp.strip().split()
    if not words:
        return None
    first_raw = words[0]
    first = first_raw.rstrip(",.")
    if not first_raw.endswith(",") and not first_raw.endswith(".") and len(words) > 1:
        return None
    if (first.istitle() and first.isalpha()
            and first.lower() not in _GREETINGS
            and first.lower() not in _NOT_NAMES):
        return first
    return None

@dataclass
class ChatState:
    partner_name: str = None
    partner_age: str = None
    said_19: bool = False
    name_sent: bool = False
    asked_russian: bool = False
    confirmed_russian: bool = False
    russian_unhandled: int = 0
    stage: int = 1
    age_validated: bool = False
    _sent: set = field(default_factory=set)

def _can_send(text: str, sent_set: set) -> bool:
    """Проверяет, можно ли отправить сообщение (не было ли уже отправлено)"""
    return text not in sent_set


async def send_once(page, text, messages, state, role="own"):
    if not _can_send(text, state._sent):
        log(f"  SKIP repeat: '{text}'")
        return False
    await human_type(page, text)
    messages.append({"role": role, "content": text})
    state._sent.add(text)
    return True

def check_filters(text: str, skip_underage: bool = False) -> str:
    """Проверяет текст на фильтры. Возвращает причину или None."""
    if is_ukrainian(text):
        return "украинский язык"
    if is_muslim(text):
        return "мусульманская лексика"
    if is_dismissive(text):
        return "грубость/отказ"
    if not skip_underage and is_underage(text):
        return "несовершеннолетняя"
    return None

async def _chat_alive(page) -> bool:
    """Проверяет, жив ли чат (видимо поле ввода, нет кнопки нового чата)."""
    input_field = await page.query_selector(INPUT_FIELD)
    input_visible = False
    try:
        input_visible = input_field and await input_field.is_visible()
    except:
        pass
    new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
    new_chat_visible = False
    try:
        new_chat_visible = new_chat_btn and await new_chat_btn.is_visible()
    except:
        pass
    return input_visible and not new_chat_visible

async def stage_greeting(page, count, messages, state):
    """Стадия 1: Приветствие + Возраст. Возвращает count или None (завершить чат)."""
    if count == 0:
        if await send_once(page, "привет", messages, state, role="own"):
            count += 1

    resp, count, resp_time = await wait_for_partner_msg(page, count, messages, timeout=10)

    if resp is None:
        print("ПРОПУСК: нет ответа на 'привет' (таймаут/чат завершён)")
        return None

    f = check_filters(resp)
    if f:
        print(f"ПРОПУСК: {f} в '{resp}'")
        await end_chat(page)
        return None

    resp_lower = resp.lower()
    log(f"=== Stage 1: анализ ответа: '{resp}' ===")

    target_ages = [17, 18, 19]
    initial_ages = [int(s) for s in re.findall(r'\d+', resp)]
    underage = [a for a in initial_ages if 0 < a < 17]
    if underage:
        print(f"ПРОПУСК: несовершеннолетняя ({underage}) в '{resp}'")
        await end_chat(page)
        return None

    age_already_known = any(a in target_ages for a in initial_ages)

    is_age_q = is_age_question(resp)
    is_zovut = any(p in resp_lower for p in ZOVUT_PATTERNS)
    is_name_q = any(p in resp_lower for p in NAME_ASK_PATTERNS)
    is_self_intro = is_self_introduction(resp)
    is_nice = any(p in resp_lower for p in NICE_TO_MEET_PATTERNS)
    is_from_q = any(p in resp_lower for p in FROM_ASK_PATTERNS) and not ("откуда" in resp_lower and "знаешь" in resp_lower)
    is_and_you = any(p in resp_lower for p in AND_YOU_PATTERNS)
    is_how = any(p in resp_lower for p in HOW_ARE_YOU_PATTERNS)

    said_19 = False

    if is_age_q:
        log("  -> age question, answering '19'")
        if await send_once(page, "19", messages, state, role="own"):
            said_19 = True
            count += 1
        if not age_already_known:
            if await send_once(page, "тебе сколько?", messages, state, role="own"):
                count += 1
    elif is_zovut:
        if await send_once(page, "по имени", messages, state, role="own"):
            count += 1
    elif is_name_q and not _name_already_sent(messages):
        if _partner_name_received(messages):
            if await send_once(page, "Максим", messages, state, role="own"):
                count += 1
        else:
            if await send_once(page, "Максим, тебя?", messages, state, role="own"):
                count += 1
    elif is_self_intro and age_already_known:
        if await send_once(page, "Максим 19", messages, state, role="own"):
            said_19 = True
            count += 1
    elif is_self_intro and not _name_already_sent(messages):
        if _partner_name_received(messages):
            if await send_once(page, "Максим", messages, state, role="own"):
                count += 1
        else:
            if await send_once(page, "Максим, тебя?", messages, state, role="own"):
                count += 1
    elif is_nice:
        if await send_once(page, "взаимно", messages, state, role="own"):
            count += 1
        already_asked_age = any("сколько лет" in m.get("content", "") for m in messages if m["role"] == "own")
        if not age_already_known and not already_asked_age:
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
    elif is_from_q:
        if await send_once(page, "Уже в гости собралась", messages, state, role="own"):
            count += 1
        already_asked_age = any("сколько лет" in m.get("content", "") for m in messages if m["role"] == "own")
        if not age_already_known and not already_asked_age:
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
    elif is_and_you:
        if is_confirmation_question(resp):
            if await send_once(page, "да", messages, state, role="own"):
                count += 1
        else:
            if not said_19 and not _already_sent_19(messages):
                if await send_once(page, "19", messages, state, role="own"):
                    said_19 = True
                    count += 1
            else:
                if await send_once(page, "Тож", messages, state, role="own"):
                    count += 1
        if not age_already_known:
            # Подождать 10 сек — может сама напишет возраст
            followup, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if followup:
                fu_ages = [int(s) for s in re.findall(r'\d+', followup)]
                if any(a in target_ages for a in fu_ages):
                    state.partner_age = str([a for a in fu_ages if a in target_ages][0])
                    log(f"  [Stage 1] Age from follow-up: {state.partner_age}")
                    state.said_19 = said_19
                    return count
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
    elif is_how:
        if await send_once(page, "норм, ты как?", messages, state, role="own"):
            count += 1
        if not age_already_known:
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
    elif not age_already_known:
        if await send_once(page, "сколько лет", messages, state, role="own"):
            count += 1

    if age_already_known:
        state.partner_age = str([a for a in initial_ages if a in target_ages][0])
        if not said_19 and not _already_sent_19(messages):
            if any(p in resp_lower for p in ["тебе", "тебя", "вас"]):
                if await send_once(page, "19", messages, state, role="own"):
                    said_19 = True
                    count += 1
        state.said_19 = said_19
        if is_self_intro or is_name_q:
            state.name_sent = True
        log(f"  [Stage 1] Age from first reply: {state.partner_age}")
        return count

    log("  [Stage 1] Waiting for age...")
    age_text, count, age_resp_time = await wait_for_partner_msg(page, count, messages, timeout=30)
    log(f"  [Stage 1] Got: '{age_text}' ({age_resp_time:.1f}s)")

    if age_text is None:
        print("ПРОПУСК: нет ответа на вопрос о возрасте")
        await end_chat(page)
        return None

    f = check_filters(age_text)
    if f:
        print(f"ПРОПУСК: {f} в ответе на возраст: '{age_text}'")
        await end_chat(page)
        return None

    age_text_lower = age_text.lower()

    if any(p in age_text_lower for p in NAME_ASK_PATTERNS) and not _name_already_sent(messages):
        if _partner_name_received(messages):
            if await send_once(page, "Максим", messages, state, role="own"):
                count += 1
        else:
            if await send_once(page, "Максим, тебя?", messages, state, role="own"):
                count += 1
        state.name_sent = True

        name_resp, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
        if name_resp is None:
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
            age_text, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if age_text is None:
                print("ПРОПУСК: нет ответа на вопрос о возрасте")
                return None
            ages = [int(s) for s in re.findall(r'\d+', age_text)]
            is_target = any(a in target_ages for a in ages)
            log(f"  [Stage 1] Age: text='{age_text}', ages={ages}, target={is_target}")
            if is_target:
                state.partner_age = str([a for a in ages if a in target_ages][0])
                print(f"ПОДХОДИТ ({ages})!")
                state.said_19 = said_19
                return count
            else:
                if ages:
                    print(f"ПРОПУСК: возраст {ages} не в диапазоне [17,18,19]")
                    await end_chat(page)
                    return None
                print("ПРОПУСК: нет возраста в ответе")
                return None

        name_resp_ages = [int(s) for s in re.findall(r'\d+', name_resp)]
        if any(a in target_ages for a in name_resp_ages):
            state.partner_age = str([a for a in name_resp_ages if a in target_ages][0])
            if any(p in name_resp.lower() for p in AND_YOU_PATTERNS) and not said_19 and not _already_sent_19(messages):
                if await send_once(page, "19", messages, state, role="own"):
                    said_19 = True
                    count += 1
            print(f"ПОДХОДИТ ({name_resp_ages})!")
            state.said_19 = said_19
            return count
        if name_resp_ages:
            print(f"ПРОПУСК: возраст {name_resp_ages} не в диапазоне [17,18,19]")
            await end_chat(page)
            return None

        if any(p in name_resp.lower() for p in AND_YOU_PATTERNS):
            if not said_19:
                if await send_once(page, "19", messages, state, role="own"):
                    said_19 = True
                    count += 1

        if await send_once(page, "сколько лет", messages, state, role="own"):
            count += 1
        age_text, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
        if age_text is None:
            print("ПРОПУСК: нет ответа на повторный вопрос о возрасте")
            return None

    ages = [int(s) for s in re.findall(r'\d+', age_text)]
    is_target = any(a in target_ages for a in ages)
    log(f"  [Stage 1] Age: text='{age_text}', ages={ages}, target={is_target}")

    if is_target:
        state.partner_age = str([a for a in ages if a in target_ages][0])
        print(f"ПОДХОДИТ ({ages})!")

        if is_self_introduction(age_text):
            if await send_once(page, "Максим 19", messages, state, role="own"):
                said_19 = True
                state.name_sent = True
                count += 1

        age_text_has_and_you = any(p in age_text_lower for p in AND_YOU_PATTERNS)
        resp_has_and_you = any(p in resp_lower for p in AND_YOU_PATTERNS)

        if age_text_has_and_you and not said_19 and not _already_sent_19(messages):
            if await send_once(page, "19", messages, state, role="own"):
                said_19 = True
                count += 1

        if not resp_has_and_you and not age_text_has_and_you and is_age_question(age_text):
            if await send_once(page, "тебе сколько?", messages, state, role="own"):
                count += 1
            age_text2, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if age_text2:
                ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                if any(a in target_ages for a in ages2):
                    state.partner_age = str([a for a in ages2 if a in target_ages][0])
                    print(f"ПОДХОДИТ ({ages2})!")
                else:
                    await end_chat(page)
                    return None

        state.said_19 = said_19
        return count
    else:
        if ages:
            print(f"ПРОПУСК: возраст {ages} не в диапазоне [17,18,19]")
            await end_chat(page)
            return None

        tl = age_text.lower()
        is_from_q2 = any(p in tl for p in FROM_ASK_PATTERNS) and not ("откуда" in tl and "знаешь" in tl)
        is_name_q2 = any(p in tl for p in NAME_ASK_PATTERNS)
        is_nice2 = any(p in tl for p in NICE_TO_MEET_PATTERNS)
        is_how_q2 = any(p in tl for p in HOW_ARE_YOU_PATTERNS)
        is_and_you_q2 = any(p in tl for p in AND_YOU_PATTERNS)
        is_age_q2 = is_age_question(age_text)

        if is_from_q2:
            if await send_once(page, "Уже в гости собралась", messages, state, role="own"):
                count += 1
            reply, count, _ = await wait_for_partner_msg(page, count, messages, timeout=15)
            if reply:
                rf = check_filters(reply)
                if rf:
                    print(f"ПРОПУСК: {rf}")
                    await end_chat(page)
                    return None
                reply_ages = [int(s) for s in re.findall(r'\d+', reply)]
                if any(a in target_ages for a in reply_ages):
                    state.partner_age = str([a for a in reply_ages if a in target_ages][0])
                    print(f"ПОДХОДИТ ({reply_ages})!")
                    return count
            await asyncio.sleep(5)
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
            age_text2, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if age_text2 is None:
                print("ПРОПУСК: нет ответа на повторный 'сколько лет'")
                return None
            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
            if any(a in target_ages for a in ages2):
                state.partner_age = str([a for a in ages2 if a in target_ages][0])
                print(f"ПОДХОДИТ ({ages2})!")
                return count
            else:
                await end_chat(page)
                return None

        elif is_name_q2 and not _name_already_sent(messages):
            if _partner_name_received(messages):
                if await send_once(page, "Максим", messages, state, role="own"):
                    count += 1
            else:
                if await send_once(page, "Максим, тебя?", messages, state, role="own"):
                    count += 1
            name_resp, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if name_resp is None:
                print("ПРОПУСК: нет ответа на 'Максим, тебя?'")
                return None
            name_resp_ages = [int(s) for s in re.findall(r'\d+', name_resp)]
            if any(a in target_ages for a in name_resp_ages):
                state.partner_age = str([a for a in name_resp_ages if a in target_ages][0])
                print(f"ПОДХОДИТ ({name_resp_ages})!")
                state.said_19 = said_19
                return count
            if name_resp_ages:
                print(f"ПРОПУСК: возраст {name_resp_ages} не в диапазоне [17,18,19]")
                await end_chat(page)
                return None
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
            age_text2, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if age_text2 is None:
                print("ПРОПУСК: нет ответа на повторный 'сколько лет'")
                return None
            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
            if any(a in target_ages for a in ages2):
                state.partner_age = str([a for a in ages2 if a in target_ages][0])
                print(f"ПОДХОДИТ ({ages2})!")
                return count
            await end_chat(page)
            return None

        elif is_nice2:
            if await send_once(page, "взаимно", messages, state, role="own"):
                count += 1
            reply, count, _ = await wait_for_partner_msg(page, count, messages, timeout=15)
            if reply:
                rf = check_filters(reply)
                if rf:
                    print(f"ПРОПУСК: {rf}")
                    await end_chat(page)
                    return None
                reply_ages = [int(s) for s in re.findall(r'\d+', reply)]
                if any(a in target_ages for a in reply_ages):
                    state.partner_age = str([a for a in reply_ages if a in target_ages][0])
                    print(f"ПОДХОДИТ ({reply_ages})!")
                    return count
            await asyncio.sleep(5)
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
            age_text2, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if age_text2 is None:
                print("ПРОПУСК: нет ответа на повторный 'сколько лет'")
                return None
            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
            if any(a in target_ages for a in ages2):
                state.partner_age = str([a for a in ages2 if a in target_ages][0])
                print(f"ПОДХОДИТ ({ages2})!")
                return count
            await end_chat(page)
            return None

        elif is_how_q2:
            if await send_once(page, "норм, ты как?", messages, state, role="own"):
                count += 1
            reply, count, _ = await wait_for_partner_msg(page, count, messages, timeout=15)
            if reply:
                rf = check_filters(reply)
                if rf:
                    print(f"ПРОПУСК: {rf}")
                    await end_chat(page)
                    return None
                reply_ages = [int(s) for s in re.findall(r'\d+', reply)]
                if any(a in target_ages for a in reply_ages):
                    state.partner_age = str([a for a in reply_ages if a in target_ages][0])
                    print(f"ПОДХОДИТ ({reply_ages})!")
                    return count
            await asyncio.sleep(5)
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
            age_text2, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if age_text2 is None:
                print("ПРОПУСК: нет ответа на повторный 'сколько лет'")
                return None
            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
            if any(a in target_ages for a in ages2):
                state.partner_age = str([a for a in ages2 if a in target_ages][0])
                print(f"ПОДХОДИТ ({ages2})!")
                return count
            await end_chat(page)
            return None

        elif is_and_you_q2:
            if await send_once(page, "19", messages, state, role="own"):
                said_19 = True
            # Подождать 10 сек — может сама напишет возраст
            followup, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if followup:
                fu_ages = [int(s) for s in re.findall(r'\d+', followup)]
                if any(a in target_ages for a in fu_ages):
                    state.partner_age = str([a for a in fu_ages if a in target_ages][0])
                    print(f"ПОДХОДИТ ({fu_ages})!")
                    state.said_19 = said_19
                    return count
                # Не年龄 — тогда спросить
            if await send_once(page, "тебе сколько?", messages, state, role="own"):
                count += 1
            age_text2, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if age_text2 is None:
                print("ПРОПУСК: нет ответа на 'тебе сколько?'")
                return None
            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
            if any(a in target_ages for a in ages2):
                state.partner_age = str([a for a in ages2 if a in target_ages][0])
                print(f"ПОДХОДИТ ({ages2})!")
                state.said_19 = said_19
                return count
            await end_chat(page)
            return None

        elif is_age_q2:
            if not said_19:
                if await send_once(page, "19", messages, state, role="own"):
                    said_19 = True
                    count += 1
            if await send_once(page, "тебе сколько?", messages, state, role="own"):
                count += 1
            age_text2, count, _ = await wait_for_partner_msg(page, count, messages, timeout=10)
            if age_text2 is None:
                print("ПРОПУСК: нет ответа на 'тебе сколько?'")
                return None
            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
            if any(a in target_ages for a in ages2):
                state.partner_age = str([a for a in ages2 if a in target_ages][0])
                print(f"ПОДХОДИТ ({ages2})!")
                state.said_19 = said_19
                return count
            await end_chat(page)
            return None

        else:
            log(f"  [Stage 1] Irrelevant response, re-asking age once")
            if await send_once(page, "сколько лет", messages, state, role="own"):
                count += 1
            age_text2, count, _ = await wait_for_partner_msg(page, count, messages, timeout=15)
            if age_text2 is None:
                print("ПРОПУСК: нет ответа на повторный вопрос о возрасте")
                return None
            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
            if any(a in target_ages for a in ages2):
                state.partner_age = str([a for a in ages2 if a in target_ages][0])
                print(f"ПОДХОДИТ ({ages2})!")
                state.said_19 = said_19
                return count
            print("ПРОПУСК: собеседник не ответила на вопрос о возрасте")
            await end_chat(page)
            return None

async def stage_names(page, count, messages, state):
    """Стадия 2: Обмен именами."""
    if state.partner_age:
        state.age_validated = True
    log(f"[Stage 2] name_sent={state.name_sent}, partner_name={state.partner_name}")

    if state.partner_name:
        return count

    if not state.name_sent:
        import time as _time
        _deadline = _time.time() + 10
        name_asked_by_partner = False

        while _time.time() < _deadline:
            remaining = _deadline - _time.time()
            if remaining <= 0:
                break
            resp, count, _ = await wait_for_partner_msg(page, count, messages, timeout=min(30, remaining))

            if resp is None:
                if await _chat_alive(page):
                    continue
                return None

            f = check_filters(resp, skip_underage=True)
            if f:
                print(f"ПРОПУСК: {f} в '{resp}'")
                await end_chat(page)
                return None

            if is_age_question(resp) or any(p in resp.lower() for p in AND_YOU_PATTERNS) or resp.strip().lower() in _SHORT_AND_YOU:
                if not state.said_19:
                    if await send_once(page, "19", messages, state, role="own"):
                        state.said_19 = True
                        count += 1
                _deadline = _time.time() + 10
                continue

            if is_self_introduction(resp):
                state.partner_name = resp
                log(f"[Stage 2] Partner intro: '{resp}'")
            else:
                words = resp.strip().split()
                if (len(words) == 1 and words[0].isalpha()
                        and words[0].lower() not in _GREETINGS
                        and words[0].lower() not in _NOT_NAMES):
                    state.partner_name = resp
                    log(f"[Stage 2] Partner name: '{resp}'")

            is_zovut = any(p in resp.lower() for p in ZOVUT_PATTERNS)
            if is_zovut:
                if await send_once(page, "по имени", messages, state, role="own"):
                    count += 1
                _deadline = _time.time() + 10
                continue
            is_name_q = any(p in resp.lower() for p in NAME_ASK_PATTERNS)
            if is_name_q:
                name_asked_by_partner = True
            if is_name_q or state.partner_name:
                break

            _tl = resp.lower()
            if any(p in _tl for p in FROM_ASK_PATTERNS) and not ("откуда" in _tl and "знаешь" in _tl):
                if await send_once(page, "Уже в гости собралась", messages, state, role="own"):
                    count += 1
                _deadline = _time.time() + 10
                continue
            elif any(p in _tl for p in NICE_TO_MEET_PATTERNS):
                if await send_once(page, "взаимно", messages, state, role="own"):
                    count += 1
                _deadline = _time.time() + 10
                continue
            elif any(p in _tl for p in HOW_ARE_YOU_PATTERNS):
                if await send_once(page, "норм, ты как?", messages, state, role="own"):
                    count += 1
                _deadline = _time.time() + 10
                continue
            elif any(p in _tl for p in WHAT_ARE_YOU_DOING_PATTERNS):
                if await send_once(page, "Бездельничаю", messages, state, role="own"):
                    count += 1
                _deadline = _time.time() + 10
                continue

        if name_asked_by_partner or state.partner_name or _partner_name_received(messages):
            if _partner_name_received(messages):
                log(f"[Stage 2] Partner name received, answering 'Максим'")
                if await send_once(page, "Максим", messages, state, role="own"):
                    state.name_sent = True
                    count += 1
            else:
                log(f"[Stage 2] {'Partner asked name' if name_asked_by_partner else 'Partner has name'}, answering 'Максим, тебя?'")
                if await send_once(page, "Максим, тебя?", messages, state, role="own"):
                    state.name_sent = True
                    count += 1
        else:
            if state.said_19:
                if not _name_already_sent(messages):
                    log("[Stage 2] Answered age, proactively asking name")
                    if await send_once(page, "Максим, тебя?", messages, state, role="own"):
                        state.name_sent = True
                        count += 1
                else:
                    log("[Stage 2] Name already sent (manual), skipping")
                    state.name_sent = True
            else:
                log("[Stage 2] No name or age question within 10s, skipping to stage 3")
                state.name_sent = True
                state.stage = 3
                return count

    resp, count, _ = await wait_for_partner_msg(page, count, messages, timeout=15)

    if resp is None:
        log("[Stage 2] No response to name question")
        state.stage = 3
        return count

    f = check_filters(resp, skip_underage=True)
    if f:
        print(f"ПРОПУСК: {f} в '{resp}'")
        await end_chat(page)
        return None

    if is_self_introduction(resp):
        state.partner_name = resp
        log(f"[Stage 2] Partner intro: '{resp}'")
    else:
        words = resp.strip().split()
        if (len(words) == 1 and words[0].isalpha()
                and words[0].lower() not in _GREETINGS
                and words[0].lower() not in _NOT_NAMES):
            state.partner_name = resp
            log(f"[Stage 2] Partner name: '{resp}'")
        elif (len(words) == 2 and words[0].lower() == "я"
              and words[1].isalpha()
              and words[1].lower() not in _GREETINGS
              and words[1].lower() not in _NOT_NAMES):
            state.partner_name = words[1]
            log(f"[Stage 2] Partner name from 'я {words[1]}': '{words[1]}'")
        elif _extracted := _extract_name_first_word(resp):
            state.partner_name = _extracted
            log(f"[Stage 2] Partner name from first word: '{state.partner_name}'")
        else:
            log(f"[Stage 2] Not a name: '{resp}', will handle in stage 3")

    if state.partner_name:
        _rl = resp.lower()
        if any(p in _rl for p in NICE_TO_MEET_PATTERNS):
            if await send_once(page, "взаимно", messages, state, role="own"):
                count += 1
        elif any(p in _rl for p in HOW_ARE_YOU_PATTERNS):
            if await send_once(page, "норм, ты как?", messages, state, role="own"):
                count += 1
        elif any(p in _rl for p in FROM_ASK_PATTERNS) and not ("откуда" in _rl and "знаешь" in _rl):
            if await send_once(page, "Уже в гости собралась", messages, state, role="own"):
                count += 1

    if state.partner_name and not state.asked_russian:
        if await send_once(page, "русская?", messages, state, role="own"):
            state.asked_russian = True
            count += 1

    followup, count, _ = await wait_for_partner_msg(page, count, messages, timeout=5)
    if followup is not None:
        log(f"[Stage 2] Follow-up after name: '{followup}'")
        fu_lower = followup.lower()
        if any(p in fu_lower for p in NICE_TO_MEET_PATTERNS):
            if await send_once(page, "взаимно", messages, state, role="own"):
                count += 1
        elif any(p in fu_lower for p in HOW_ARE_YOU_PATTERNS):
            if await send_once(page, "норм, ты как?", messages, state, role="own"):
                count += 1
        elif any(p in fu_lower for p in WHAT_ARE_YOU_DOING_PATTERNS):
            if await send_once(page, "Бездельничаю", messages, state, role="own"):
                count += 1
        elif any(p in fu_lower for p in AND_YOU_PATTERNS) or followup.strip().lower() in _SHORT_AND_YOU:
            if not _already_sent_19(messages):
                if await send_once(page, "19", messages, state, role="own"):
                    count += 1
        elif any(p in fu_lower for p in FROM_ASK_PATTERNS) and not ("откуда" in fu_lower and "знаешь" in fu_lower):
            if await send_once(page, "Уже в гости собралась", messages, state, role="own"):
                count += 1
        elif any(p in fu_lower for p in RUSSIAN_CONFIRM_PATTERNS):
            if await send_once(page, "ура", messages, state, role="own"):
                state.asked_russian = False
                state.confirmed_russian = True
                count += 1

    state.stage = 3
    return count

async def stage_free_chat(page, count, messages, state):
    """Стадия 3: Свободное общение (бывший enter_wait_mode). Возвращает True когда чат завершён."""
    if state.partner_age:
        state.age_validated = True
    lc = count
    name_asked = _name_already_sent(messages)
    name_pre_set = name_asked
    from_asked = False
    nice_to_meet = False

    log(f"  [Stage 3] age={state.partner_age}, count={count}")

    # --- Фаза 1: 60 секунд — наблюдаем за ключевыми вопросами ---
    silence_sec = 0
    age_triggered = False
    for _ in range(60):
        await asyncio.sleep(1)
        if not await _chat_alive(page):
            reason = "chat_ended"
            log(f"  [Stage 3] CHAT ENDED (phase1): {reason}")
            if len(messages) > 10:
                await save_chat_log(messages, state.partner_age)
            return True
        msgs = await page.query_selector_all(MESSAGES)
        if len(msgs) > lc:
            await hover_msg(page, msgs[-1])
            silence_sec = 0
            for i in range(lc, len(msgs)):
                t = await msgs[i].inner_text()
                r = await get_msg_role(page, msgs[i])
                ro = "own" if r == "self" else "other"
                messages.append({"role": ro, "content": t})
                if ro == "other":
                    log(f"  [Stage 3] msg: '{t}'")
                    await speak(t, female=True)
                    f = check_filters(t, skip_underage=True)
                    if f:
                        log(f"  [Stage 3] CHAT ENDED (phase1): {f} in '{t}'")
                        await end_chat(page)
                        return True
                    tl = t.lower()
                    is_name = any(p in tl for p in NAME_ASK_PATTERNS) or is_self_introduction(t) or (
                        len(t.split()) == 1 and t.split()[0].isalpha()
                        and t.split()[0].lower() not in _GREETINGS
                        and t.split()[0].lower() not in _NOT_NAMES
                    )
                    is_from = any(p in tl for p in FROM_ASK_PATTERNS) and not ("откуда" in tl and "знаешь" in tl)
                    is_nice = any(p in tl for p in NICE_TO_MEET_PATTERNS)
                    is_age = is_age_question(t)
                    is_and_you = any(p in tl for p in AND_YOU_PATTERNS) or t.strip().lower() in _SHORT_AND_YOU
                    is_how = any(p in tl for p in HOW_ARE_YOU_PATTERNS)
                    is_doing = any(p in tl for p in WHAT_ARE_YOU_DOING_PATTERNS)

                    if is_name and not name_asked:
                        log(f"  [Stage 3] TRIGGER: name-ask")
                        name_asked = True
                    elif is_from and not from_asked:
                        log(f"  [Stage 3] TRIGGER: from-ask")
                        from_asked = True
                    elif is_nice and not nice_to_meet:
                        log(f"  [Stage 3] TRIGGER: nice-to-meet")
                        nice_to_meet = True
                    elif is_age:
                        log(f"  [Stage 3] TRIGGER: age-ask")
                        age_triggered = True
                    elif state.asked_russian and any(p in tl for p in RUSSIAN_CONFIRM_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: russian-confirm -> 'ура'")
                        await send_once(page, "ура", messages, state, role="own")
                        state.asked_russian = False
                        state.confirmed_russian = True
                    elif state.confirmed_russian and t.strip().lower() in ("ты?", "а ты?"):
                        log(f"  [Stage 3] TRIGGER: russian-and-you -> 'тоже'")
                        await send_once(page, "тоже", messages, state, role="own")
                    elif is_and_you:
                        if not _already_sent_19(messages):
                            log(f"  [Stage 3] TRIGGER: and-you -> '19'")
                            await send_once(page, "19", messages, state, role="own")
                    elif is_how:
                        log(f"  [Stage 3] TRIGGER: how-are-you -> 'норм, ты как?'")
                        await send_once(page, "норм, ты как?", messages, state, role="own")
                    elif is_doing:
                        log(f"  [Stage 3] TRIGGER: what-are-you-doing -> 'Бездельничаю'")
                        await send_once(page, "Бездельничаю", messages, state, role="own")
                    elif any(p in tl for p in LOOKING_FOR_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: looking-for -> 'тебя конечно'")
                        await send_once(page, "тебя конечно", messages, state, role="own")
                    elif state.asked_russian:
                        state.russian_unhandled += 1
                        if state.russian_unhandled >= 3:
                            log(f"  [Stage 3] Reset asked_russian (3 unhandled)")
                            state.asked_russian = False
            lc = len(msgs)
        else:
            silence_sec += 1
            if silence_sec >= 7 and not _already_sent_19(messages) and not state.age_validated:
                log(f"  [Stage 3] TRIGGER: silence 7s -> '19'")
                await send_once(page, "19", messages, state, role="own")
                lc = len(msgs)
        if (not name_pre_set and name_asked) or from_asked or nice_to_meet or age_triggered:
            break

    log(f"  [Stage 3] phase1 done: name={name_asked} from={from_asked} nice={nice_to_meet} age={age_triggered}")

    if from_asked:
        await send_once(page, "Уже в гости собралась", messages, state, role="own")
    elif nice_to_meet:
        await send_once(page, "взаимно", messages, state, role="own")
    elif age_triggered and not _already_sent_19(messages):
        await send_once(page, "19", messages, state, role="own")
    elif name_asked and not _name_already_sent(messages):
        if _partner_name_received(messages):
            await send_once(page, "Максим", messages, state, role="own")
        else:
            await send_once(page, "Максим, тебя?", messages, state, role="own")

    name_sent = name_asked
    and_you_answered = False

    # --- Фаза 2: бесконечный цикл — отвечаем на всё ---
    while True:
        await asyncio.sleep(1)

        if not await _chat_alive(page):
            reason = "chat_ended"
            log(f"  [Stage 3] CHAT ENDED: {reason}")
            if len(messages) > 10:
                await save_chat_log(messages, state.partner_age)
            return True

        msgs = await page.query_selector_all(MESSAGES)
        if len(msgs) > lc:
            await hover_msg(page, msgs[-1])
            for i in range(lc, len(msgs)):
                t = await msgs[i].inner_text()
                r = await get_msg_role(page, msgs[i])
                ro = "own" if r == "self" else "other"
                messages.append({"role": ro, "content": t})
                if ro == "other":
                    log(f"  [Stage 3] msg: '{t}'")
                    await speak(t, female=True)
                    f = check_filters(t, skip_underage=True)
                    if f:
                        log(f"  [Stage 3] CHAT ENDED: {f} in '{t}'")
                        await end_chat(page)
                        return True
                    tl = t.lower()
                    is_question = (
                        "?" in t
                        or any(p in tl for p in NAME_ASK_PATTERNS)
                        or any(p in tl for p in FROM_ASK_PATTERNS)
                        or any(p in tl for p in NICE_TO_MEET_PATTERNS)
                        or is_age_question(t)
                    )
                    words_t = t.split()
                    is_single_name = (
                        len(words_t) == 1
                        and words_t[0].isalpha()
                        and words_t[0].lower() not in _GREETINGS
                        and words_t[0].lower() not in _NOT_NAMES
                    )
                    if not name_asked and any(p in tl for p in NAME_ASK_PATTERNS) and not _name_already_sent(messages):
                        name_asked = True
                        if _partner_name_received(messages):
                            if await send_once(page, "Максим", messages, state, role="own"):
                                name_sent = True
                        else:
                            if await send_once(page, "Максим, тебя?", messages, state, role="own"):
                                name_sent = True
                        lc = len(msgs)
                        break
                    elif not name_asked and is_self_introduction(t) and not _name_already_sent(messages):
                        log(f"  [Stage 3] self-intro: '{t}'")
                        name_asked = True
                        if _partner_name_received(messages):
                            if await send_once(page, "Максим", messages, state, role="own"):
                                name_sent = True
                        else:
                            if await send_once(page, "Максим, тебя?", messages, state, role="own"):
                                name_sent = True
                        lc = len(msgs)
                        break
                    elif not from_asked and any(p in tl for p in FROM_ASK_PATTERNS) and not ("откуда" in tl and "знаешь" in tl):
                        from_asked = True
                        if await send_once(page, "Уже в гости собралась", messages, state, role="own"):
                            pass
                        lc = len(msgs)
                        break
                    elif not nice_to_meet and any(p in tl for p in NICE_TO_MEET_PATTERNS):
                        nice_to_meet = True
                        if await send_once(page, "взаимно", messages, state, role="own"):
                            pass
                        lc = len(msgs)
                        break
                    elif is_age_question(t):
                        if await send_once(page, "19", messages, state, role="own"):
                            pass
                        lc = len(msgs)
                        break
                    elif any(p in tl for p in COMPLIMENT_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: compliment -> 'спасибо)'")
                        await send_once(page, "спасибо)", messages, state, role="own")
                    elif is_confirmation_question(t):
                        log(f"  [Stage 3] TRIGGER: confirmation -> 'да'")
                        await send_once(page, "да", messages, state, role="own")
                    elif "?" in tl and "есть" in tl and not and_you_answered and any(p in tl for p in AND_YOU_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: and-you+есть -> 'нет'")
                        and_you_answered = True
                        await send_once(page, "нет", messages, state, role="own")
                    elif any(p in tl for p in WHAT_ARE_YOU_DOING_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: what-are-you-doing -> 'Бездельничаю'")
                        await send_once(page, "Бездельничаю", messages, state, role="own")
                        lc = len(msgs)
                        break
                    elif any(p in tl for p in LOOKING_FOR_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: looking-for -> 'тебя конечно'")
                        await send_once(page, "тебя конечно", messages, state, role="own")
                        lc = len(msgs)
                        break
                    elif any(p in tl for p in HOW_ARE_YOU_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: how-are-you -> 'норм, ты как?'")
                        await send_once(page, "норм, ты как?", messages, state, role="own")
                        lc = len(msgs)
                        break
                    elif name_sent and is_single_name and state.partner_name is None:
                        state.partner_name = t
                        log(f"  [Stage 3] Partner name saved: '{t}'")
                        if not state.asked_russian:
                            if await send_once(page, "русская?", messages, state, role="own"):
                                state.asked_russian = True
                        lc = len(msgs)
                        break
                    elif state.asked_russian and any(p in tl for p in RUSSIAN_CONFIRM_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: russian-confirm -> 'ура'")
                        if await send_once(page, "ура", messages, state, role="own"):
                            state.asked_russian = False
                            state.confirmed_russian = True
                        lc = len(msgs)
                        break
                    elif state.confirmed_russian and t.strip().lower() in ("ты?", "а ты?"):
                        log(f"  [Stage 3] TRIGGER: russian-and-you -> 'тоже'")
                        await send_once(page, "тоже", messages, state, role="own")
                        lc = len(msgs)
                        break
                    elif any(p in tl for p in TG_CONTINUE_PATTERNS):
                        log(f"  [Stage 3] TRIGGER: tg-continue -> 'давай, скинь ссылку'")
                        await send_once(page, "давай, скинь ссылку", messages, state, role="own")
                        lc = len(msgs)
                        break
                    else:
                        if state.asked_russian:
                            state.russian_unhandled += 1
                            if state.russian_unhandled >= 3:
                                log(f"  [Stage 3] Reset asked_russian (3 unhandled)")
                                state.asked_russian = False
                        log(f"  [Stage 3] UNHANDLED: '{t}' (tl='{tl}')")
            lc = len(msgs)

UKRAINIAN_TRIGGERS = ["привiт", "привіт", "тобi", "тобі"]

def is_ukrainian(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    for trigger in UKRAINIAN_TRIGGERS:
        if trigger in t:
            return True
    # "украинка/украинец" только как признание ("я украинка"), не как вопрос ("ты украинец?")
    if re.search(r'\bя\b.*украинк', t) or re.search(r'\bя\b.*украинец', t):
        return True
    return False

MUSLIM_SUBSTRINGS = [
    "ассалам", "алейкум", "асаляму", "алайкум",
    "машаллах", "ма ша аллер", "ин ша аллах", "иншаллах",
    "бисмилля", "субханаллах", "алхамдулиллях",
    "халаль", "харом", "харам",
    "мусульман", "мусульмани",
]

def is_muslim(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    for p in MUSLIM_SUBSTRINGS:
        if p in t:
            # "мусульман" требует самоидентификации (я мусульманка/мусульманин)
            # Вопросы про мусульман не триггерят
            if p in ("мусульман", "мусульмани") and "?" in t:
                if not re.search(r'\bя\b', t):
                    continue
            return True
    return False

DISMISSIVE_PATTERNS = [
    "молчи", "заткнись", "закройся",
    "уйди", "пошел", "пошёл",
    "отстань", "надоел", "надоела",
    "задолбал", "задолбала", "задолбали",
    "не хочу", "некогда", "занята", "занят",
    "нет времени", "не время",
    "сам дурак", "тупой", "идиот",
    "достал", "достала",
    "иди отсюда", "иди нах", "пошёл нах", "пошел нах",
    "многа",
]

UNDERAGE_PATTERNS = [
    "несовершеннолетн", "не достигла совершеннолетия",
    "не достиг совершеннолетия", "мне нет 18",
    "мне нет восемнадцати", "мне ещё 18",
    "мне еще 18", "мне не 18",
    "мне 1[0-7]", "мне шестнадцать",
    "мне пятнадцать", "мне четырнадцать",
    "мне 10", "мне 11", "мне 12", "мне 13", "мне 14", "мне 15", "мне 16",
]

def is_dismissive(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    for p in DISMISSIVE_PATTERNS:
        if p in t:
            return True
    return False

def is_underage(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    for p in UNDERAGE_PATTERNS:
        if p in t:
            return True
    # Проверяем числа в начале текста (например "14 я маленькая")
    leading = re.match(r'^(\d{2,})', t)
    if leading:
        age = int(leading.group(1))
        if 0 < age < 17:
            return True
    return False

def is_age_question(text: str) -> bool:
    """Проверяет, спрашивает ли собеседник возраст бота.
    Только явные вопросы про возраст."""
    if not text:
        return False
    t = text.lower().strip()
    for p in AGE_ASK_PATTERNS:
        if p in t:
            return True
    return False

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=[f"--remote-debugging-port={REMOTE_DEBUGGING_PORT}"]
        )

        pages = browser.pages
        page = pages[0] if pages else await browser.new_page()

        await setup_tts_toggle(page)

        tts_thread = threading.Thread(target=_tts_worker, daemon=True)
        tts_thread.start()

        stages = [stage_greeting, stage_names, stage_free_chat]

        while True:
            try:
                count = await start_new_chat(page)
                await _inject_tts_panel(page)
                chat_messages = []
                state = ChatState()

                for stage_fn in stages:
                    result = await stage_fn(page, count, chat_messages, state)
                    if result is None:
                        break
                    count = result

                await end_chat(page)

                log(f"[Main] Chat ended. age={state.partner_age}, name={state.partner_name}, msgs={len(chat_messages)}")

            except Exception as e:
                error_msg = str(e)
                if "Timeout" in error_msg and "INPUT_FIELD" in error_msg:
                    print(f"Таймаут поиска собеседника. Ждем 10 секунд перед повтором...")
                    await asyncio.sleep(10)
                else:
                    print(f"Ошибка в цикле: {e}")
                    await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
