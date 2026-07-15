import asyncio
import os
import re
import random
import time
import winsound
import threading
import queue
from datetime import datetime
from playwright.async_api import async_playwright
from config import USER_DATA_DIR, REMOTE_DEBUGGING_PORT

DEBUG = True

def log(msg):
    if DEBUG:
        print(f"  [DEBUG] {msg}", flush=True)

# --- TTS (озвучка сообщений) ---
_tts_queue = queue.Queue()
_tts_ready = False
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
    _tts_queue.put((text, female))

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
    await page.click(INPUT_FIELD)
    # Быстрая печать с минимальной задержкой
    await page.type(INPUT_FIELD, text, delay=random.randint(10, 30))
    await page.keyboard.press("Enter")
    print(f"Отправлено: {text}")
    await speak(text, female=False)

async def get_msg_role(page, msg_element):
    """Определяет, отправлено ли сообщение ботом (self) или собеседником"""
    return await msg_element.evaluate("""el => {
        const block = el.closest('.mess_block');
        if (!block) return 'unknown';
        if (block.classList.contains('self')) return 'self';
        if (block.classList.contains('nekto')) return 'nekto';
        return 'unknown';
    }""")

async def wait_for_partner_msg(page, last_count, all_messages: list = None, timeout: float = None):
    """Ждет нового сообщения от собеседника с опциональным таймаутом"""
    import time
    start_time = time.time()
    
    while True:
        elapsed = time.time() - start_time
        if elapsed > 5:
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
                return None, last_count, 0
        
        current_msgs = await page.query_selector_all(MESSAGES)
        if len(current_msgs) > last_count:
            for i in range(last_count, len(current_msgs)):
                role = await get_msg_role(page, current_msgs[i])
                if role != 'self':
                    text = await current_msgs[i].inner_text()
                    log(f"  [wait_for_partner] got: '{text}' (role={role})")
                    print(f"Собеседник: {text}")
                    await speak(text, female=True)
                    if all_messages is not None:
                        all_messages.append({"role": "other", "content": text})
                    response_time = time.time() - start_time
                    return text, i + 1, response_time
            # Все новые сообщения — свои (ввёл пользователь вручную)
            last_count = len(current_msgs)
        
        if timeout is not None and (time.time() - start_time) > timeout:
            return None, last_count, 0
        
        await asyncio.sleep(0.2)

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
            return len(msgs)
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
    "скока", "скоко", "сколька", "сколко",
    "скока тебе", "скока лет",
    # "а тебе"/"а те" удалены — это "and you?", а не вопрос возраста
    # Славянские формы
    "самой", "самому",
    # Опечатки
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
    "имя", "как называть",
]


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
    return False

FROM_ASK_PATTERNS = [
    "откуда", "где живешь", "где ты живешь",
    "с какого города", "из какого города", "какого ты города",
    "город", "откуда ты",
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
    "тебе?", "тебя?",
]

WHAT_ARE_YOU_DOING_PATTERNS = [
    "что делаешь", "чем занят", "чем занимаешься",
    "что сейчас делаешь", "чем шумишь",
]

CONFIRMATION_PATTERNS = ["да", "верно", "точно", "правда", "ага"]

COMPLIMENT_PATTERNS = [
    "красивое имя", "крутое имя", "хорошее имя",
    "прикольное имя", "милое имя", "стрange имя",
    "какое имя", "имя крутое", "имя красивое",
    "классное имя", "интересное имя",
]

def is_confirmation_question(text: str) -> bool:
    t = text.lower().strip()
    if not any(p in t for p in ["а ты"]):
        return False
    # Check if ends with a confirmation word (e.g. "а ты русский да")
    words = t.split()
    if words and words[-1] in CONFIRMATION_PATTERNS:
        return True
    # Check for "да" in the middle/end part of the message (e.g. "а ты русский да?")
    after_atyu = t.split("а ты", 1)
    if len(after_atyu) > 1 and any(p in after_atyu[1] for p in CONFIRMATION_PATTERNS):
        return True
    return False

def _name_already_sent(chat_messages):
    for msg in chat_messages:
        if "максим" in msg.get("content", "").lower():
            return True
    return False

async def enter_wait_mode(page, count, chat_messages, label_age):
    """После обмена возрастом: ждёт имя, 'откуда', вопрос про возраст, отвечает, логирует до конца чата"""
    lc = count
    name_asked = False
    from_asked = False
    nice_to_meet = False
    age_asked = False

    log(f"  [enter_wait_mode] age={label_age}, count={count}")
    for _ in range(60):
        await asyncio.sleep(1)
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
            reason = "input_hidden" if not input_visible else "new_chat_btn"
            log(f"  [wait_mode] CHAT ENDED (loop1): {reason}")
            if len(chat_messages) > 10:
                await save_chat_log(chat_messages, label_age)
            return True
        msgs = await page.query_selector_all(MESSAGES)
        if len(msgs) > lc:
            for i in range(lc, len(msgs)):
                t = await msgs[i].inner_text()
                r = await get_msg_role(page, msgs[i])
                ro = "own" if r == "self" else "other"
                chat_messages.append({"role": ro, "content": t})
                if ro == "other":
                    log(f"  [wait_mode] msg: '{t}'")
                    await speak(t, female=True)
                    if is_ukrainian(t):
                        log(f"  [wait_mode] CHAT ENDED (loop1): ukrainian in '{t}'")
                        await end_chat(page)
                        return True
                    if is_muslim(t):
                        log(f"  [wait_mode] CHAT ENDED (loop1): muslim in '{t}'")
                        await end_chat(page)
                        return True
                    tl = t.lower()
                    if any(p in tl for p in AND_YOU_PATTERNS):
                        log(f"  [wait_mode] and-you in loop1: '{t}'")
                        await human_type(page, "19")
                        chat_messages.append({"role": "own", "content": "19"})
                    if not name_asked and not from_asked:
                        if any(p in tl for p in NAME_ASK_PATTERNS):
                            name_asked = True
                        elif is_self_introduction(t):
                            name_asked = True
                        if any(p in tl for p in FROM_ASK_PATTERNS):
                            from_asked = True
                        if any(p in tl for p in NICE_TO_MEET_PATTERNS):
                            nice_to_meet = True
                        if is_age_question(t):
                            age_asked = True
            lc = len(msgs)
        if name_asked or from_asked or nice_to_meet or age_asked:
            break

    log(f"  [wait_mode] loop1 done: name={name_asked} from={from_asked} nice={nice_to_meet} age={age_asked}")

    if name_asked and not _name_already_sent(chat_messages):
        await human_type(page, "Максим, тебя?")
        chat_messages.append({"role": "own", "content": "Максим, тебя?"})
    elif from_asked:
        await human_type(page, "Уже в гости собралась")
        chat_messages.append({"role": "own", "content": "Уже в гости собралась"})
    elif nice_to_meet:
        await human_type(page, "взаимно")
        chat_messages.append({"role": "own", "content": "взаимно"})
    elif age_asked:
        await human_type(page, "19")
        chat_messages.append({"role": "own", "content": "19"})

    name_sent = name_asked
    name_received_time = None
    russkiy_sent = False
    russkiy_answered = False
    and_you_answered = False

    while True:
        await asyncio.sleep(1)

        if name_sent and name_received_time is not None and not russkiy_sent:
            if time.time() - name_received_time >= 5:
                russkiy_sent = True
                await human_type(page, "Русская??")
                chat_messages.append({"role": "own", "content": "Русская??"})

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
            reason = "input_hidden" if not input_visible else "new_chat_btn"
            log(f"  [wait_mode] CHAT ENDED: {reason} (input={input_visible}, new_chat={new_chat_visible})")
            if len(chat_messages) > 10:
                await save_chat_log(chat_messages, label_age)
            return True
        msgs = await page.query_selector_all(MESSAGES)
        if len(msgs) > lc:
            for i in range(lc, len(msgs)):
                t = await msgs[i].inner_text()
                r = await get_msg_role(page, msgs[i])
                ro = "own" if r == "self" else "other"
                chat_messages.append({"role": ro, "content": t})
                if ro == "other":
                    log(f"  [wait_mode] msg: '{t}'")
                    await speak(t, female=True)
                    if is_ukrainian(t):
                        log(f"  [wait_mode] CHAT ENDED: ukrainian detected in '{t}'")
                        await end_chat(page)
                        return True
                    if is_muslim(t):
                        log(f"  [wait_mode] CHAT ENDED: muslim detected in '{t}'")
                        await end_chat(page)
                        return True
                    if is_dismissive(t):
                        log(f"  [wait_mode] CHAT ENDED: dismissive detected in '{t}'")
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
                    if russkiy_sent and not russkiy_answered:
                        russkiy_answered = True
                        tl_check = t.lower().strip()
                        first_word = tl_check.split()[0] if tl_check.split() else tl_check
                        is_negative = (
                            first_word in ("нет", "не", "no")
                            or "не русск" in tl_check
                            or "не русская" in tl_check
                            or "не русский" in tl_check
                        )
                        is_positive = first_word in ("да", "ага", "угу", "yes", "конечно", "точно", "русская", "русский", "ну")
                        if not is_positive:
                            _words = tl_check.split()
                            if len(_words) > 1 and _words[1] in ("да", "ага", "угу", "конечно"):
                                is_positive = True
                        if is_positive:
                            await human_type(page, "Оке")
                            chat_messages.append({"role": "own", "content": "Оке"})
                            continue
                        elif is_negative:
                            await human_type(page, "Кто")
                            chat_messages.append({"role": "own", "content": "Кто"})
                            continue
                    if name_sent and not name_received_time and not is_question:
                        name_received_time = time.time()
                        lc = len(msgs)
                        continue
                    if not name_asked and any(p in tl for p in NAME_ASK_PATTERNS) and not _name_already_sent(chat_messages):
                        name_asked = True
                        await human_type(page, "Максим, тебя?")
                        chat_messages.append({"role": "own", "content": "Максим, тебя?"})
                        name_sent = True
                        lc = len(msgs)
                        break
                    elif not name_asked and is_self_introduction(t) and not _name_already_sent(chat_messages):
                        log(f"  [wait_mode] self-intro in loop: '{t}'")
                        name_asked = True
                        await human_type(page, "Максим, тебя?")
                        chat_messages.append({"role": "own", "content": "Максим, тебя?"})
                        name_sent = True
                        lc = len(msgs)
                        break
                    elif not from_asked and any(p in tl for p in FROM_ASK_PATTERNS):
                        from_asked = True
                        await human_type(page, "Уже в гости собралась")
                        chat_messages.append({"role": "own", "content": "Уже в гости собралась"})
                        lc = len(msgs)
                        break
                    elif not nice_to_meet and any(p in tl for p in NICE_TO_MEET_PATTERNS):
                        nice_to_meet = True
                        await human_type(page, "взаимно")
                        chat_messages.append({"role": "own", "content": "взаимно"})
                        lc = len(msgs)
                        break
                    elif not age_asked and is_age_question(t):
                        age_asked = True
                        await human_type(page, "19")
                        chat_messages.append({"role": "own", "content": "19"})
                        lc = len(msgs)
                        break
                    elif any(p in tl for p in COMPLIMENT_PATTERNS):
                        log(f"  [wait_mode] compliment detected: '{t}'")
                        await human_type(page, "спасибо)")
                        chat_messages.append({"role": "own", "content": "спасибо)"})
                    elif is_confirmation_question(t):
                        await human_type(page, "да")
                        chat_messages.append({"role": "own", "content": "да"})
                    elif "есть" in tl and not and_you_answered and any(p in tl for p in AND_YOU_PATTERNS):
                        and_you_answered = True
                        await human_type(page, "нет")
                        chat_messages.append({"role": "own", "content": "нет"})
                    elif not and_you_answered and any(p in tl for p in AND_YOU_PATTERNS):
                        and_you_answered = True
                        await human_type(page, "Тож")
                        chat_messages.append({"role": "own", "content": "Тож"})
                        lc = len(msgs)
                        break
                    elif any(p in tl for p in WHAT_ARE_YOU_DOING_PATTERNS):
                        await human_type(page, "Бездельничаю")
                        chat_messages.append({"role": "own", "content": "Бездельничаю"})
                        lc = len(msgs)
                        break
                    else:
                        log(f"  [wait_mode] UNHANDLED msg: '{t}' (tl='{tl}')")
            lc = len(msgs)

UKRAINIAN_TRIGGERS = ["привiт", "привіт", "тобi", "тобі", "украинк", "украинец"]

def is_ukrainian(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    for trigger in UKRAINIAN_TRIGGERS:
        if trigger in t:
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
            return True
    return False

DISMISSIVE_PATTERNS = [
    "молчи", "заткнись", "закройся",
    "уйди", "пошел", "пошёл",
    "отстань", "надоел", "надоела",
    "не хочу", "некогда", "занята", "занят",
    "нет времени", "не время",
    "сам дурак", "тупой", "идиот",
    "достал", "достала",
    "иди отсюда", "иди нах", "пошёл нах", "пошел нах",
]

UNDERAGE_PATTERNS = [
    "несовершеннолетн", "не достигла совершеннолетия",
    "не достиг совершеннолетия", "мне нет 18",
    "мне нет восемнадцати", "мне ещё 18",
    "мне еще 18", "мне не 18",
    "мне 1[0-7]", "мне семнадцать", "мне шестнадцать",
    "мне пятнадцать", "мне четырнадцать",
    "мне 10", "мне 11", "мне 12", "мне 13", "мне 14", "мне 15", "мне 16", "мне 17",
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

async def wait_and_reply_age(page, count, chat_messages, partner_msg):
    """Проверяет, спросили ли возраст. Если нет — ждёт 15с, потом отвечает 19."""
    winsound.Beep(1000, 1000)
    await asyncio.sleep(0.2)
    winsound.Beep(1000, 1000)

    asked = is_age_question(partner_msg)

    if not asked:
        for _ in range(15):
            await asyncio.sleep(1)
            btn = await page.query_selector(NEW_CHAT_BUTTON)
            input_field = await page.query_selector(INPUT_FIELD)
            input_visible = False
            try:
                input_visible = input_field and await input_field.is_visible()
            except:
                pass
            new_chat_visible = False
            try:
                new_chat_visible = btn and await btn.is_visible()
            except:
                pass
            if not input_visible or new_chat_visible:
                return count
            msgs = await page.query_selector_all(MESSAGES)
            if len(msgs) > count:
                for i in range(count, len(msgs)):
                    role = await get_msg_role(page, msgs[i])
                    if role == 'self':
                        continue
                    t = await msgs[i].inner_text()
                    chat_messages.append({"role": "other", "content": t})
                    print(f"Собеседник: {t}")
                    await speak(t, female=True)
                    if is_age_question(t):
                        asked = True
                count = len(msgs)
            if asked:
                break

    await human_type(page, "19")
    chat_messages.append({"role": "own", "content": "19"})
    return count

async def main():
    async with async_playwright() as p:
        # Запускаем Chrome с использованием постоянного профиля
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=USER_DATA_DIR,
            headless=False,
            args=[f"--remote-debugging-port={REMOTE_DEBUGGING_PORT}"]
        )

        # Получаем страницу из контекста
        pages = browser.pages
        page = pages[0] if pages else await browser.new_page()

        # Запускаем TTS worker
        tts_thread = threading.Thread(target=_tts_worker, daemon=True)
        tts_thread.start()

        while True:
            try:
                # Запускаем новый чат
                count = await start_new_chat(page)
                
                # Список для сбора всех сообщений чата
                chat_messages = []

                # Проверяем, есть ли уже сообщения в чате (не отправляем "привет" повторно)
                if count == 0:
                    await human_type(page, "привет")
                    chat_messages.append({"role": "own", "content": "привет"})
                    count += 1

                # 5. Ждем ответ
                resp, count, resp_time = await wait_for_partner_msg(page, count, chat_messages, timeout=10)

                # Если чат завершен во время ожидания
                if resp is None:
                    print("ПРОПУСК: нет ответа на 'привет' (таймаут/чат завершён)")
                    continue

                if is_ukrainian(resp):
                    print(f"ПРОПУСК: украинский язык в '{resp}'")
                    await end_chat(page)
                    continue

                if is_muslim(resp):
                    print(f"ПРОПУСК: мусульманская лексика в '{resp}'")
                    await end_chat(page)
                    continue

                if is_dismissive(resp):
                    print(f"ПРОПУСК: грубость/отказ в '{resp}'")
                    await end_chat(page)
                    continue

                if is_underage(resp):
                    print(f"ПРОПУСК: несовершеннолетняя в '{resp}'")
                    await end_chat(page)
                    continue

                # 6. Проверяем, не спросила ли "откуда"
                resp_lower = resp.lower()
                is_from_question = any(p in resp_lower for p in FROM_ASK_PATTERNS)
                is_nice_to_meet = any(p in resp_lower for p in NICE_TO_MEET_PATTERNS)
                is_and_you = any(p in resp_lower for p in AND_YOU_PATTERNS)
                is_self_intro = is_self_introduction(resp)
                is_name_ask = any(p in resp_lower for p in NAME_ASK_PATTERNS)

                log(f"=== Анализ ответа: '{resp}' ===")
                log(f"  is_age_question={is_age_question(resp)}")
                log(f"  is_from_question={is_from_question}")
                log(f"  is_nice_to_meet={is_nice_to_meet}")
                log(f"  is_and_you={is_and_you}")
                log(f"  is_self_intro={is_self_intro}")
                log(f"  is_name_ask={is_name_ask}")
                log(f"  is_ukrainian={is_ukrainian(resp)}")
                log(f"  is_muslim={is_muslim(resp)}")
                log(f"  is_dismissive={is_dismissive(resp)}")

                # 6. Если собеседник уже спросил возраст — отвечаем сразу
                target_ages = [17, 18, 19]
                said_19 = False
                age_already_known = False
                age_text = None
                age_resp_time = 0

                # Проверяем, не назвал ли собеседник возраст сразу (например "19" в ответ на "привет")
                _initial_ages = [int(s) for s in re.findall(r'\d+', resp)]
                if any(a in target_ages for a in _initial_ages):
                    age_already_known = True
                    age_text = resp

                if is_age_question(resp):
                    log("  -> Ответ: age question detected, answering '19'")
                    await human_type(page, "19")
                    chat_messages.append({"role": "own", "content": "19"})
                    said_19 = True
                    count += 1
                    if not age_already_known:
                        await human_type(page, "тебе сколько?")
                        chat_messages.append({"role": "own", "content": "тебе сколько?"})
                        count += 1
                elif is_name_ask and not _name_already_sent(chat_messages):
                    log("  -> Ответ: name question detected, answering 'Максим, тебя?'")
                    await human_type(page, "Максим, тебя?")
                    chat_messages.append({"role": "own", "content": "Максим, тебя?"})
                    count += 1
                elif is_self_intro and age_already_known:
                    log(f"  -> Ответ: self-intro + age known, answering 'Максим 19'")
                    await human_type(page, "Максим 19")
                    chat_messages.append({"role": "own", "content": "Максим 19"})
                    said_19 = True
                    count += 1
                elif is_self_intro and not _name_already_sent(chat_messages):
                    log(f"  -> Ответ: self-introduction detected ('{resp}'), answering 'Максим, тебя?'")
                    await human_type(page, "Максим, тебя?")
                    chat_messages.append({"role": "own", "content": "Максим, тебя?"})
                    count += 1
                elif is_nice_to_meet:
                    log("  -> Ответ: nice to meet, answering 'взаимно'")
                    await human_type(page, "взаимно")
                    chat_messages.append({"role": "own", "content": "взаимно"})
                    count += 1
                    await human_type(page, "сколько лет")
                    chat_messages.append({"role": "own", "content": "сколько лет"})
                    count += 1
                elif is_from_question:
                    log("  -> Ответ: from question, answering 'Уже в гости собралась'")
                    await human_type(page, "Уже в гости собралась")
                    chat_messages.append({"role": "own", "content": "Уже в гости собралась"})
                    count += 1
                    await human_type(page, "сколько лет")
                    chat_messages.append({"role": "own", "content": "сколько лет"})
                    count += 1
                elif is_and_you:
                    log("  -> Ответ: and-you question")
                    if is_confirmation_question(resp):
                        await human_type(page, "да")
                        chat_messages.append({"role": "own", "content": "да"})
                    else:
                        await human_type(page, "Тож")
                        chat_messages.append({"role": "own", "content": "Тож"})
                    count += 1
                    if age_already_known:
                        log("  -> Age already known, not asking again")
                    else:
                        await human_type(page, "сколько лет")
                        chat_messages.append({"role": "own", "content": "сколько лет"})
                        count += 1
                elif not age_already_known:
                    log("  -> Ответ: no pattern matched, asking 'сколько лет'")
                    await human_type(page, "сколько лет")
                    chat_messages.append({"role": "own", "content": "сколько лет"})
                    count += 1

                # 7. Ждем ответ про возраст (таймаут 10 секунд) — если ещё не знаем
                if not age_already_known:
                    log(f"  [Жду ответ на 'сколько лет']...")
                    age_text, count, age_resp_time = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                    log(f"  [Ответ на возраст]: '{age_text}' (time={age_resp_time:.1f}s)")

                # Если чат завершен во время ожидания
                if age_text is None:
                    print("ПРОПУСК: нет ответа на вопрос о возрасте (таймаут/чат завершён)")
                    await end_chat(page)
                    continue

                if is_ukrainian(age_text):
                    print(f"ПРОПУСК: украинский язык в ответе на возраст: '{age_text}'")
                    await end_chat(page)
                    continue

                if is_muslim(age_text):
                    print(f"ПРОПУСК: мусульманская лексика в ответе на возраст: '{age_text}'")
                    await end_chat(page)
                    continue

                if is_underage(age_text):
                    print(f"ПРОПУСК: несовершеннолетняя в ответе на возраст: '{age_text}'")
                    await end_chat(page)
                    continue

                # Проверяем, не спросила ли имя вместо возраста
                age_text_lower = age_text.lower()
                if any(p in age_text_lower for p in NAME_ASK_PATTERNS) and not _name_already_sent(chat_messages):
                    await human_type(page, "Максим, тебя?")
                    chat_messages.append({"role": "own", "content": "Максим, тебя?"})
                    count += 1
                    # Ждем ответ на имя (таймаут 10 сек)
                    name_resp, count, _ = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                    if name_resp is None:
                        print("ПРОПУСК: нет ответа на вопрос о имени (таймаут/чат завершён)")
                        continue
                    # Проверяем, не назвала ли возраст в ответе на имя
                    name_resp_ages = [int(s) for s in re.findall(r'\d+', name_resp)]
                    name_resp_target = any(a in target_ages for a in name_resp_ages)
                    log(f"  [NAME_ASK] name_resp='{name_resp}', ages={name_resp_ages}, target={name_resp_target}")
                    if name_resp_target:
                        # Сказала имя + возраст сразу — ПОДХОДИТ
                        print(f"ПОДХОДИТ ({name_resp_ages})!")
                        if not said_19:
                            await human_type(page, "19")
                            chat_messages.append({"role": "own", "content": "19"})
                            said_19 = True
                            count += 1
                        await enter_wait_mode(page, count, chat_messages, str(name_resp_ages[0]))
                        continue
                    elif name_resp_ages:
                        # Сказала возраст, но не таргет (например 16) — завершаем
                        print(f"ПРОПУСК: возраст {name_resp_ages} не в диапазоне [17,18,19]")
                        log(f"  [NAME_ASK] age {name_resp_ages} not in target, ending chat")
                        await end_chat(page)
                        continue
                    # Также проверяем, не ответила ли "а тебе?" — тогда отвечаем "19"
                    name_resp_and_you = any(p in name_resp.lower() for p in AND_YOU_PATTERNS)
                    if name_resp_and_you:
                        log(f"  [NAME_ASK] name_resp also has 'and you', answering '19'")
                        await human_type(page, "19")
                        chat_messages.append({"role": "own", "content": "19"})
                        said_19 = True
                        count += 1
                    else:
                        # Только имя, без возраста — спрашиваем возраст
                        await human_type(page, "сколько лет")
                        chat_messages.append({"role": "own", "content": "сколько лет"})
                        count += 1
                    # Ждем ответ про возраст
                    age_text, count, age_resp_time = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                    if age_text is None:
                        print("ПРОПУСК: нет ответа на повторный вопрос о возрасте (таймаут/чат завершён)")
                        continue
                    ages = [int(s) for s in re.findall(r'\d+', age_text)]
                    is_target = any(a in target_ages for a in ages)
                    if is_target:
                        print(f"ПОДХОДИТ ({ages})!")
                        if not said_19:
                            await human_type(page, "19")
                            chat_messages.append({"role": "own", "content": "19"})
                            said_19 = True
                            count += 1
                        await enter_wait_mode(page, count, chat_messages, str(ages[0]))
                        continue
                    else:
                        print(f"ПРОПУСК: возраст {ages} не в диапазоне [17,18,19] (после имени)")
                        await end_chat(page)
                        continue

                # 8. Проверка возраста (17, 18, 19)
                ages = [int(s) for s in re.findall(r'\d+', age_text)]
                is_target = any(a in target_ages for a in ages)
                log(f"  [Проверка возраста]: text='{age_text}', ages={ages}, target={target_ages}, is_target={is_target}")

                if is_target:
                    print(f"ПОДХОДИТ ({ages})!")
                    resp_has_and_you = any(p in resp_lower for p in AND_YOU_PATTERNS)
                    age_text_has_and_you = any(p in age_text.lower() for p in AND_YOU_PATTERNS)
                    if not said_19 and (is_age_question(age_text) or resp_has_and_you or age_text_has_and_you):
                        log(f"  [is_target] answering '19' (age_question={is_age_question(age_text)}, and_you={resp_has_and_you}, age_text_and_you={age_text_has_and_you})")
                        await human_type(page, "19")
                        chat_messages.append({"role": "own", "content": "19"})
                        said_19 = True
                        count += 1
                    if not resp_has_and_you and not age_text_has_and_you and not age_already_known and is_age_question(age_text):
                        log(f"  [is_target] also asking 'тебе сколько?'")
                        await human_type(page, "тебе сколько?")
                        chat_messages.append({"role": "own", "content": "тебе сколько?"})
                        count += 1
                        # Ждем ответ на "тебе сколько?"
                        age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                        if age_text2 is not None:
                            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                            is_target2 = any(a in target_ages for a in ages2)
                            if is_target2:
                                print(f"ПОДХОДИТ ({ages2})!")
                                await enter_wait_mode(page, count, chat_messages, str(ages2[0]))
                                continue
                            else:
                                await end_chat(page)
                                continue
                    await enter_wait_mode(page, count, chat_messages, str(ages[0]))
                    continue
                else:
                    if ages:
                        print(f"ПРОПУСК: возраст {ages} не в диапазоне [17,18,19]")
                        await end_chat(page)
                    else:
                        asked_age = is_age_question(age_text)
                        tl_age = age_text.lower()
                        is_from_q = any(p in tl_age for p in FROM_ASK_PATTERNS)
                        is_name_q = any(p in tl_age for p in NAME_ASK_PATTERNS)
                        is_nice = any(p in tl_age for p in NICE_TO_MEET_PATTERNS)

                        if is_from_q:
                            log(f"  -> Ответ на возраст: 'откуда', отвечаем 'Уже в гости собралась'")
                            await human_type(page, "Уже в гости собралась")
                            chat_messages.append({"role": "own", "content": "Уже в гости собралась"})
                            count += 1
                            await human_type(page, "сколько лет")
                            chat_messages.append({"role": "own", "content": "сколько лет"})
                            count += 1
                            age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                            if age_text2 is None:
                                print("ПРОПУСК: нет ответа на повторный 'сколько лет' (таймаут/чат завершён)")
                                continue
                            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                            is_target2 = any(a in target_ages for a in ages2)
                        elif is_name_q and not _name_already_sent(chat_messages):
                            log(f"  -> Ответ на возраст: 'имя', отвечаем 'Максим, тебя?'")
                            await human_type(page, "Максим, тебя?")
                            chat_messages.append({"role": "own", "content": "Максим, тебя?"})
                            count += 1
                            name_resp, count, _ = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                            if name_resp is None:
                                print("ПРОПУСК: нет ответа на 'Максим, тебя?' (таймаут/чат завершён)")
                                continue
                            name_resp_ages = [int(s) for s in re.findall(r'\d+', name_resp)]
                            is_target2 = any(a in target_ages for a in name_resp_ages)
                            ages2 = name_resp_ages
                        elif is_nice:
                            log(f"  -> Ответ на возраст: 'приятно', отвечаем 'взаимно'")
                            await human_type(page, "взаимно")
                            chat_messages.append({"role": "own", "content": "взаимно"})
                            count += 1
                            await human_type(page, "сколько лет")
                            chat_messages.append({"role": "own", "content": "сколько лет"})
                            count += 1
                            age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                            if age_text2 is None:
                                print("ПРОПУСК: нет ответа на повторный 'сколько лет' (таймаут/чат завершён)")
                                continue
                            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                            is_target2 = any(a in target_ages for a in ages2)
                        elif asked_age:
                            await human_type(page, "19")
                            chat_messages.append({"role": "own", "content": "19"})
                            said_19 = True
                            await asyncio.sleep(0.5)
                            await human_type(page, "тебе сколько?")
                            chat_messages.append({"role": "own", "content": "тебе сколько?"})
                            count += 2
                            
                            age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                            
                            if age_text2 is None:
                                print("ПРОПУСК: нет ответа на 'тебе сколько?' (таймаут/чат завершён)")
                                continue
                            
                            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                            is_target2 = any(a in target_ages for a in ages2)
                        elif age_resp_time > 3:
                            await human_type(page, "ну скажи сколько лет?")
                            chat_messages.append({"role": "own", "content": "ну скажи сколько лет?"})
                            count += 1

                            age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)

                            if age_text2 is None:
                                print("ПРОПУСК: нет ответа на 'ну скажи сколько лет?' (таймаут/чат завершён)")
                                continue

                            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                            is_target2 = any(a in target_ages for a in ages2)
                        elif age_resp_time <= 3:
                            await human_type(page, "ну скажи сколько лет?")
                            chat_messages.append({"role": "own", "content": "ну скажи сколько лет?"})
                            count += 1

                            age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)

                            if age_text2 is None:
                                print("ПРОПУСК: нет ответа на 'ну скажи сколько лет?' (таймаут/чат завершён)")
                                continue

                            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                            is_target2 = any(a in target_ages for a in ages2)

                        if age_text2 and is_ukrainian(age_text2):
                            print(f"ПРОПУСК: украинский язык в '{age_text2}'")
                            await end_chat(page)
                            continue

                        if age_text2 and is_muslim(age_text2):
                            print(f"ПРОПУСК: мусульманская лексика в '{age_text2}'")
                            await end_chat(page)
                            continue

                        if is_target2:
                            print(f"ПОДХОДИТ ({ages2})!")
                            await enter_wait_mode(page, count, chat_messages, str(ages2[0]))
                            continue
                        else:
                            print(f"ПРОПУСК: возраст {ages2 if age_text2 else 'не указан'} не в диапазоне [17,18,19]")
                            await end_chat(page)

                await asyncio.sleep(1) # Пауза перед новым кругом

            except Exception as e:
                # Если ошибка поиска собеседника (таймаут) - ждем дольше перед повтором
                error_msg = str(e)
                if "Timeout" in error_msg and "INPUT_FIELD" in error_msg:
                    print(f"Таймаут поиска собеседника. Ждем 10 секунд перед повтором...")
                    await asyncio.sleep(10)
                else:
                    print(f"Ошибка в цикле: {e}")
                    await asyncio.sleep(3)

if __name__ == "__main__":
    asyncio.run(main())
