import asyncio
import re
import random
import winsound
from datetime import datetime
from playwright.async_api import async_playwright
from config import USER_DATA_DIR, REMOTE_DEBUGGING_PORT

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
        new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
        if new_chat_btn:
            try:
                is_visible = await new_chat_btn.is_visible()
                if is_visible:
                    print(f"  [Chat] Найден кнопка 'Начать новый чат' - чат завершен")
                    return None, last_count, 0
            except:
                pass
        
        current_msgs = await page.query_selector_all(MESSAGES)
        if len(current_msgs) > last_count:
            for i in range(last_count, len(current_msgs)):
                role = await get_msg_role(page, current_msgs[i])
                if role != 'self':
                    text = await current_msgs[i].inner_text()
                    print(f"Собеседник: {text}")
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
    """Начинает новый чат"""
    print("\n--- Запуск нового цикла ---")
    
    # Пробуем нажать "Начать чат" если чат завершен
    try:
        new_chat_btn = await page.wait_for_selector(NEW_CHAT_BUTTON, timeout=2000)
        if new_chat_btn:
            await new_chat_btn.click()
            print("Нажата кнопка 'Начать новый чат'")
            await asyncio.sleep(1)
    except:
        # Если кнопки нет, идем на главную и ищем основную кнопку
        await page.goto("https://nekto.me/chat/#/")
        await page.wait_for_selector(START_BUTTON)
        await page.click(START_BUTTON)
        print("Нажата кнопка поиска собеседника")
    
    # Принять правила (если выскочат)
    try:
        await page.wait_for_selector(ACCEPT_RULES, timeout=2000)
        await page.click(ACCEPT_RULES)
    except:
        pass
    
    # Ждем появления поля ввода (собеседник найден)
    # Таймаут 5 минут - достаточно для поиска собеседника
    print("Ищем собеседника...")
    try:
        await page.wait_for_selector(INPUT_FIELD, timeout=300000)
        print("Собеседник найден!")
    except Exception as e:
        print(f"Ошибка поиска собеседника: {e}")
        raise  # Пробрасываем ошибку дальше
    
    # Возвращаем количество текущих сообщений
    msgs = await page.query_selector_all(MESSAGES)
    return len(msgs)

async def end_chat(page):
    """Завершает текущий чат"""
    try:
        # Пробуем найти кнопку "Завершить чат" в шапке
        stop = await page.wait_for_selector("button:has-text('Завершить чат')", timeout=2000)
        if stop:
            await stop.click()
            await asyncio.sleep(0.5)
            # Подтверждение
            confirm = await page.wait_for_selector("button.swal2-confirm", timeout=2000)
            if confirm:
                await confirm.click()
                print("Чат завершен")
                return
    except:
        pass
    
    # Если не нашли кнопку завершения - чат уже может быть завершен
    print("Не удалось найти кнопку завершения (возможно чат уже завершен)")

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
    
    print(f"Лог чата сохранён: {filename}")
    return filename

AGE_ASK_PATTERNS = [
    # Стандартные формы
    "сколько тебе", "а тебе", "тебе сколько",
    "а тебе сколько", "сколько лет",
    "сколько тебя",
    "твой возраст",
    "а твой", "твой",
    "а ты", "а у тебя", "у тебя",
    "а ваш", "а вам",
    "вам", "вам сколько",
    "самой", "самому",
    "тебе", "тебя",
    # Короткие формы (в контексте возраста — точно про "а тебе")
    "а те",
    # Фонетические опечатки (и/е)
    "а тибе", "а тибя",
    "тибе", "тибя",
    "скока", "скоко", "сколька", "сколко",
    "скока тебе", "скока лет",
    # Опечатки по клавиатуре ЙЦУКЕН (б/ю/ь — соседние клавиши)
    "теюе", "а теюе", "теье", "а теье",
    # Слитное написание
    "атебе", "ате",
]

_TE_WORD_RE = re.compile(r'\bте\b', re.IGNORECASE)

NAME_ASK_PATTERNS = [
    "как тебя зовут", "как зовут", "как звать",
    "твое имя", "твоё имя",
    "а тебя", "представься",
    "как тебя", "а как тебя",
    "имя", "как называть",
]

FROM_ASK_PATTERNS = [
    "откуда",
]

async def enter_wait_mode(page, count, chat_messages, label_age):
    """После обмена возрастом: ждёт имя или 'откуда', отвечает, логирует до конца чата"""
    lc = count
    name_asked = False
    from_asked = False

    for _ in range(60):
        await asyncio.sleep(1)
        new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
        if new_chat_btn:
            try:
                if await new_chat_btn.is_visible():
                    if len(chat_messages) > 10:
                        await save_chat_log(chat_messages, label_age)
                    return True
            except:
                pass
        msgs = await page.query_selector_all(MESSAGES)
        if len(msgs) > lc:
            for i in range(lc, len(msgs)):
                t = await msgs[i].inner_text()
                r = await get_msg_role(page, msgs[i])
                ro = "own" if r == "self" else "other"
                chat_messages.append({"role": ro, "content": t})
                print(f"[{'Я' if ro == 'own' else 'Собеседник'}] {t}")
                if ro == "other":
                    if is_ukrainian(t):
                        print(f"Украинский язык обнаружен: '{t}'. Завершаю чат.")
                        await end_chat(page)
                        return True
                    if not name_asked and not from_asked:
                        tl = t.lower()
                        if any(p in tl for p in NAME_ASK_PATTERNS):
                            name_asked = True
                        if any(p in tl for p in FROM_ASK_PATTERNS):
                            from_asked = True
            lc = len(msgs)
        if name_asked or from_asked:
            break

    if name_asked:
        print("Спросила имя — отвечаю 'Максим'...")
        await human_type(page, "Максим")
        chat_messages.append({"role": "own", "content": "Максим"})
        await asyncio.sleep(0.3)
        await human_type(page, "Тебя?")
        chat_messages.append({"role": "own", "content": "Тебя?"})
    elif from_asked:
        print("Спросила 'откуда' — отвечаю 'Уже в гости собралась'...")
        await human_type(page, "Уже в гости собралась")
        chat_messages.append({"role": "own", "content": "Уже в гости собралась"})
    else:
        print("Вопрос не задан — логирую")

    print("=== РЕЖИМ ОЖИДАНИЯ ===")
    print("Бот логирует сообщения. Для завершения нажмите Ctrl+C")

    while True:
        await asyncio.sleep(1)
        new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
        if new_chat_btn:
            try:
                if await new_chat_btn.is_visible():
                    if len(chat_messages) > 10:
                        await save_chat_log(chat_messages, label_age)
                    return True
            except:
                pass
        msgs = await page.query_selector_all(MESSAGES)
        if len(msgs) > lc:
            for i in range(lc, len(msgs)):
                t = await msgs[i].inner_text()
                r = await get_msg_role(page, msgs[i])
                ro = "own" if r == "self" else "other"
                chat_messages.append({"role": ro, "content": t})
                print(f"[{'Я' if ro == 'own' else 'Собеседник'}] {t}")
                if ro == "other" and is_ukrainian(t):
                    print(f"Украинский язык обнаружен: '{t}'. Завершаю чат.")
                    await end_chat(page)
                    return True
            lc = len(msgs)

UKRAINIAN_CHARS = re.compile(r'[ґїє]', re.IGNORECASE)

UKRAINIAN_WORDS = [
    "привіт", "привітик",
    "паляниця",
    "слава україні", "слава нації",
    "хлопець", "дівчина",
    "гарно", "гарний", "гарна",
    "дуже",
    "його",
    "який", "яка", "яке", "які",
    "цей", "ця", "це", "ці",
    "але",
    "що",
    "він", "вона", "воно",
    "ні",
]

UKRAINIAN_SUBSTRINGS = [
    "привiт",
    "слава украини",
    "херсон", "харків", "київ", "львів", "дніпро", "одеса", "крим",
    "москаль", "рашист", "русский военный корабль",
    "бандера", "азов",
]

def is_ukrainian(text: str) -> bool:
    if not text:
        return False
    t = text.lower().strip()
    if UKRAINIAN_CHARS.search(t):
        return True
    for p in UKRAINIAN_SUBSTRINGS:
        if p in t:
            return True
    for p in UKRAINIAN_WORDS:
        if re.search(r'\b' + re.escape(p) + r'\b', t):
            return True
    return False

def is_age_question(text: str) -> bool:
    """Проверяет, спрашивает ли собеседник возраст бота"""
    if not text:
        return False
    t = text.lower()
    for p in AGE_ASK_PATTERNS:
        if p in t:
            return True
    if _TE_WORD_RE.search(t):
        return True
    return False

async def wait_and_reply_age(page, count, chat_messages, partner_msg):
    """Проверяет, спросили ли возраст. Если нет — ждёт 15с, потом отвечает 19."""
    winsound.Beep(1000, 1000)
    await asyncio.sleep(0.2)
    winsound.Beep(1000, 1000)

    asked = is_age_question(partner_msg)

    if not asked:
        print("Жду 15 секунд (или пока спросит возраст)...")
        for _ in range(15):
            await asyncio.sleep(1)
            btn = await page.query_selector(NEW_CHAT_BUTTON)
            if btn:
                try:
                    if await btn.is_visible():
                        return count
                except:
                    pass
            msgs = await page.query_selector_all(MESSAGES)
            if len(msgs) > count:
                for i in range(count, len(msgs)):
                    role = await get_msg_role(page, msgs[i])
                    if role == 'self':
                        continue
                    t = await msgs[i].inner_text()
                    chat_messages.append({"role": "other", "content": t})
                    print(f"Собеседник: {t}")
                    if is_age_question(t):
                        asked = True
                count = len(msgs)
            if asked:
                break

    if asked:
        print("Спросила возраст — отвечаю '19'...")
    else:
        print("15 секунд прошло — отвечаю '19'...")
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

        while True:
            try:
                # Запускаем новый чат
                count = await start_new_chat(page)
                
                # Список для сбора всех сообщений чата
                chat_messages = []

                # 4. Пишем "привет" - сразу без задержки
                await human_type(page, "привет")
                chat_messages.append({"role": "own", "content": "привет"})
                count += 1 # Наше сообщение

                # 5. Ждем ответ
                print("Ждем ответ на 'привет'...")
                resp, count, resp_time = await wait_for_partner_msg(page, count, chat_messages)

                # Если чат завершен во время ожидания
                if resp is None:
                    print("Чат завершен собеседником. Начинаю новый...")
                    continue

                if is_ukrainian(resp):
                    print(f"Украинский язык обнаружен: '{resp}'. Завершаю чат.")
                    await end_chat(page)
                    continue

                # 6. Проверяем, не спросила ли "откуда"
                resp_lower = resp.lower()
                is_from_question = any(p in resp_lower for p in FROM_ASK_PATTERNS)

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
                    print(f"Собеседник указал возраст в первом ответе: {_initial_ages}")

                if is_age_question(resp):
                    print("Собеседник спросил возраст — отвечаю '19' и спрашиваю в ответ...")
                    await human_type(page, "19")
                    chat_messages.append({"role": "own", "content": "19"})
                    said_19 = True
                    count += 1
                    if not age_already_known:
                        await human_type(page, "тебе сколько?")
                        chat_messages.append({"role": "own", "content": "тебе сколько?"})
                        count += 1
                elif is_from_question:
                    print("Собеседник спросил 'откуда' — отвечаю 'Уже в гости собралась'...")
                    await human_type(page, "Уже в гости собралась")
                    chat_messages.append({"role": "own", "content": "Уже в гости собралась"})
                    count += 1
                    # Также спрашиваем возраст
                    await human_type(page, "сколько лет")
                    chat_messages.append({"role": "own", "content": "сколько лет"})
                    count += 1
                elif not age_already_known:
                    await human_type(page, "сколько лет")
                    chat_messages.append({"role": "own", "content": "сколько лет"})
                    count += 1

                # 7. Ждем ответ про возраст (таймаут 10 секунд) — если ещё не знаем
                if age_already_known:
                    print(f"Возраст уже известен (пропускаем ожидание)")
                else:
                    print("Ждем возраст...")
                    age_text, count, age_resp_time = await wait_for_partner_msg(page, count, chat_messages, timeout=10)

                # Если чат завершен во время ожидания
                if age_text is None:
                    # Проверяем, завершен ли чат или просто таймаут
                    new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
                    if new_chat_btn:
                        is_visible = await new_chat_btn.is_visible()
                        if is_visible:
                            print("Чат завершен собеседником. Начинаю новый...")
                            continue

                if age_text and is_ukrainian(age_text):
                    print(f"Украинский язык обнаружен: '{age_text}'. Завершаю чат.")
                    await end_chat(page)
                    continue
                    
                    # Таймаут - молчит 10 секунд, спрашиваем ещё раз
                    print("Собеседник молчит 10 секунд. Переспрашиваем...")
                    await human_type(page, "ну скажи сколько лет?")
                    chat_messages.append({"role": "own", "content": "ну скажи сколько лет?"})
                    count += 1
                    
                    # Ждем ответ ещё раз (таймаут 10 секунд)
                    age_text, count, age_resp_time = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                    
                    if age_text is None:
                        print("Собеседник не ответил. Начинаю новый чат...")
                        continue

                print(f"Собеседник ответил: {age_text} (время ответа: {age_resp_time:.1f}с)")

                # 8. Проверка возраста (17, 18, 19)
                ages = [int(s) for s in re.findall(r'\d+', age_text)]

                is_target = any(a in target_ages for a in ages)

                if is_target:
                    print(f"ПОДХОДИТ ({ages})!")
                    if said_19 or age_already_known:
                        await enter_wait_mode(page, count, chat_messages, str(ages[0]))
                    else:
                        await human_type(page, "19")
                        chat_messages.append({"role": "own", "content": "19"})
                        count += 1
                        await enter_wait_mode(page, count, chat_messages, str(ages[0]))
                    continue
                else:
                    # Возраст не назван или не подходит - переспрашиваем или уточняем
                    print(f"Возраст не назван или не подходит: '{age_text}' (найдено: {ages})")

                    # Проверяем, есть ли в ответе числа (возможно возраст в другом формате)
                    if ages:
                        # Возраст есть, но не 17-19
                        print("Возраст не подходит (не 17-19). Завершаю чат.")
                        await end_chat(page)
                    else:
                        # Проверяем, спрашивает ли собеседник о возрасте бота
                        asked_age = is_age_question(age_text)
                        
                        if asked_age:
                            # Собеседник спрашивает возраст бота - отвечаем "19"
                            print("Собеседник спрашивает возраст - отвечаю '19'...")
                            await human_type(page, "19")
                            chat_messages.append({"role": "own", "content": "19"})
                            said_19 = True
                            await asyncio.sleep(0.5)
                            await human_type(page, "тебе сколько?")
                            chat_messages.append({"role": "own", "content": "тебе сколько?"})
                            count += 2
                            
                            # Ждем ответ (таймаут 10 секунд)
                            age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                            
                            if age_text2 is None:
                                print("Собеседник не ответил. Начинаю новый чат...")
                                continue
                            
                            print(f"Собеседник ответил: {age_text2}")
                            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                            is_target2 = any(a in target_ages for a in ages2)
                        # Возраст не назван - переспрашиваем только если ответ был медленным (>3 сек)
                        elif age_resp_time > 3:
                            print("Переспрашиваем возраст...")
                            await human_type(page, "ну скажи сколько лет?")
                            chat_messages.append({"role": "own", "content": "ну скажи сколько лет?"})
                            count += 1

                            # Ждем ответ ещё раз (таймаут 10 секунд)
                            print("Ждем возраст (повторно)...")
                            age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)

                            if age_text2 is None:
                                # Проверяем, завершен ли чат или просто таймаут
                                new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
                                if new_chat_btn:
                                    is_visible = await new_chat_btn.is_visible()
                                    if is_visible:
                                        print("Чат завершен собеседником. Начинаю новый...")
                                        continue
                                
                                print("Собеседник не ответил. Начинаю новый чат...")
                                continue


                            print(f"Собеседник ответил: {age_text2}")
                            ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                            is_target2 = any(a in target_ages for a in ages2)
                        elif age_resp_time <= 3:
                            # Быстрый ответ (<3 сек) но без возраста - просто ждём ещё
                            # Не переспрашиваем сразу, даём собеседнику время
                            print("Быстрый ответ - ждём ещё сообщений...")
                            age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                            
                            if age_text2 is None:
                                # Таймаут 10 секунд - молчит, переспрашиваем
                                new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
                                if new_chat_btn:
                                    is_visible = await new_chat_btn.is_visible()
                                    if is_visible:
                                        print("Чат завершен собеседником. Начинаю новый...")
                                        continue
                                
                                print("Собеседник молчит. Переспрашиваем...")
                                await human_type(page, "ну скажи сколько лет?")
                                chat_messages.append({"role": "own", "content": "ну скажи сколько лет?"})
                                count += 1
                                
                                # Ждем ответ ещё раз (таймаут 10 секунд)
                                age_text2, count, age_resp_time2 = await wait_for_partner_msg(page, count, chat_messages, timeout=10)
                                
                                if age_text2 is None:
                                    print("Собеседник не ответил. Начинаю новый чат...")
                                    continue
                                
                                print(f"Собеседник ответил: {age_text2}")
                                ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                                is_target2 = any(a in target_ages for a in ages2)
                            else:
                                # Пришло новое сообщение - проверяем возраст
                                print(f"Собеседник ответил: {age_text2}")
                                ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                                is_target2 = any(a in target_ages for a in ages2)

                        if age_text2 and is_ukrainian(age_text2):
                            print(f"Украинский язык обнаружен: '{age_text2}'. Завершаю чат.")
                            await end_chat(page)
                            continue

                        if is_target2:
                            print(f"ПОДХОДИТ ({ages2})!")
                            if said_19 or age_already_known:
                                await enter_wait_mode(page, count, chat_messages, str(ages2[0]))
                            else:
                                await human_type(page, "19")
                                chat_messages.append({"role": "own", "content": "19"})
                                count += 1
                                await enter_wait_mode(page, count, chat_messages, str(ages2[0]))
                            continue
                        else:
                            print(f"Возраст всё ещё не подходит: '{age_text2}'. Завершаю чат.")
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
