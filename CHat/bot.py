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

async def wait_for_partner_msg(page, last_count, all_messages: list = None, timeout: float = None):
    """Ждет нового сообщения от собеседника с опциональным таймаутом"""
    import time
    start_time = time.time()
    
    while True:
        # Проверяем кнопку "Начать новый чат" - только если она видимая
        # Это надёжный индикатор того, что чат действительно завершен
        new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
        if new_chat_btn:
            try:
                is_visible = await new_chat_btn.is_visible()
                if is_visible:
                    print(f"  [Chat] Найден кнопка 'Начать новый чат' - чат завершен")
                    return None, last_count
            except:
                pass  # Если не можем проверить, продолжаем ждать
        
        current_msgs = await page.query_selector_all(MESSAGES)
        if len(current_msgs) > last_count:
            # Берем текст последнего сообщения
            text = await current_msgs[-1].inner_text()
            print(f"Собеседник: {text}")
            
            # Сохраняем сообщение в список (если передан)
            if all_messages is not None:
                all_messages.append({"role": "other", "content": text})
            
            # Возвращаем время ответа
            response_time = time.time() - start_time
            return text, len(current_msgs), response_time
        
        # Проверяем таймаут
        if timeout is not None and (time.time() - start_time) > timeout:
            return None, last_count, 0  # Таймаут истёк
        
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

                # 6. Пишем "сколько лет" - сразу без задержки
                await human_type(page, "сколько лет")
                chat_messages.append({"role": "own", "content": "сколько лет"})
                count += 1

                # 7. Ждем ответ про возраст (таймаут 10 секунд)
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
                target_ages = [17, 18, 19]

                is_target = any(a in target_ages for a in ages)

                if is_target:
                    # Проверяем, сколько времени прошло с последнего сообщения
                    # Если меньше 3 секунд - не переспрашиваем
                    print(f"ПОДХОДИТ ({ages})! Отправляю сообщения и перехожу в режим ожидания.")
                    # Воспроизводим звуковой сигнал (громкий и длинный)
                    winsound.Beep(1000, 1000)  # Частота 1000 Гц, длительность 1000 мс
                    await asyncio.sleep(0.2)
                    winsound.Beep(1000, 1000)  # Второй сигнал
                    await human_type(page, "неужели")
                    chat_messages.append({"role": "own", "content": "неужели"})
                    await asyncio.sleep(0.5)
                    await human_type(page, "небольшой тест")
                    chat_messages.append({"role": "own", "content": "небольшой тест"})
                    await asyncio.sleep(0.5)
                    await human_type(page, "любимый мультик детства??")
                    chat_messages.append({"role": "own", "content": "любимый мультик детства??"})
                    
                    # Переходим в режим ожидания - просто логируем сообщения
                    print("=== РЕЖИМ ОЖИДАНИЯ ===")
                    print("Бот логирует сообщения. Для завершения нажмите Ctrl+C")
                    
                    # Ждём пока чат не завершится
                    while True:
                        await asyncio.sleep(1)
                        
                        # Проверяем, не завершен ли чат
                        new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
                        if new_chat_btn:
                            is_visible = await new_chat_btn.is_visible()
                            if is_visible:
                                print("Чат завершен. Начинаю новый поиск...")
                                break
                        
                        # Проверяем новые сообщения и логируем их
                        current_msgs = await page.query_selector_all(MESSAGES)
                        if len(current_msgs) > count:
                            # Получаем все новые сообщения
                            for i in range(count, len(current_msgs)):
                                msg_text = await current_msgs[i].inner_text()
                                # Определяем роль
                                msg_classes = await current_msgs[i].get_attribute("class")
                                role = "own" if "self" in msg_classes else "other"
                                role_name = "Я" if role == "own" else "Собеседник"
                                chat_messages.append({"role": role, "content": msg_text})
                                print(f"[{role_name}] {msg_text}")
                            count = len(current_msgs)
                    
                    # Сохраняем лог если сообщений больше 10
                    if len(chat_messages) > 10:
                        await save_chat_log(chat_messages, str(ages[0]))
                    
                    continue  # Начинаем новый цикл
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
                        age_question_patterns = ["сколько лет", "сколько тебе", "твой возраст", "как стар", "как стар ты"]
                        is_age_question = any(pattern in age_text.lower() for pattern in age_question_patterns)
                        
                        if is_age_question:
                            # Собеседник спрашивает возраст бота - отвечаем "19"
                            print("Собеседник спрашивает возраст - отвечаю '19'...")
                            await human_type(page, "19")
                            chat_messages.append({"role": "own", "content": "19"})
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

                        if is_target2:
                            print(f"ПОДХОДИТ ({ages2})! Отправляю сообщения и перехожу в режим ожидания.")
                            # Воспроизводим звуковой сигнал
                            winsound.Beep(1000, 1000)
                            await asyncio.sleep(0.2)
                            winsound.Beep(1000, 1000)
                            await human_type(page, "неужели")
                            chat_messages.append({"role": "own", "content": "неужели"})
                            await asyncio.sleep(0.5)
                            await human_type(page, "небольшой тест")
                            chat_messages.append({"role": "own", "content": "небольшой тест"})
                            await asyncio.sleep(0.5)
                            await human_type(page, "любимый мультик детства??")
                            chat_messages.append({"role": "own", "content": "любимый мультик детства??"})
                            
                            # Переходим в режим ожидания - просто логируем сообщения
                            print("=== РЕЖИМ ОЖИДАНИЯ ===")
                            print("Бот логирует сообщения. Для завершения нажмите Ctrl+C")
                            
                            # Ждём пока чат не завершится
                            while True:
                                await asyncio.sleep(1)
                                
                                # Проверяем, не завершен ли чат
                                new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
                                if new_chat_btn:
                                    is_visible = await new_chat_btn.is_visible()
                                    if is_visible:
                                        print("Чат завершен. Начинаю новый поиск...")
                                        break
                                
                                # Проверяем новые сообщения и логируем их
                                current_msgs = await page.query_selector_all(MESSAGES)
                                print(f"  [DEBUG] Найдено сообщений: {len(current_msgs)}, last count: {count}")
                                
                                if len(current_msgs) > count:
                                    # Получаем все новые сообщения
                                    print(f"  [DEBUG] Новых сообщений: {len(current_msgs) - count}")
                                    for i in range(count, len(current_msgs)):
                                        msg_element = current_msgs[i]
                                        msg_text = await msg_element.inner_text()
                                        
                                        # Получаем HTML для отладки
                                        outer_html = await msg_element.evaluate("el => el.outerHTML")
                                        print(f"  [DEBUG] Сообщение {i}: '{msg_text}'")
                                        print(f"  [DEBUG] HTML: {outer_html[:200]}...")
                                        
                                        # Определяем роль через JavaScript - ищем ближайший .mess_block
                                        role_info = await msg_element.evaluate("""
                                            el => {
                                                const block = el.closest('.mess_block');
                                                if (!block) return { found: false };
                                                return {
                                                    found: true,
                                                    hasSelf: block.classList.contains('self'),
                                                    hasNekto: block.classList.contains('nekto'),
                                                    classes: block.className
                                                };
                                            }
                                        """)
                                        
                                        # Отладка
                                        print(f"  [DEBUG] Роль: {role_info}")
                                        
                                        if role_info.get('hasSelf'):
                                            role = "own"
                                        elif role_info.get('hasNekto'):
                                            role = "other"
                                        else:
                                            # Фоллбэк - считаем что это собеседник
                                            role = "other"
                                        
                                        role_name = "Я" if role == "own" else "Собеседник"
                                        chat_messages.append({"role": role, "content": msg_text})
                                        print(f"[{role_name}] {msg_text}")
                                    count = len(current_msgs)
                            
                            # Сохраняем лог если сообщений больше 10
                            if len(chat_messages) > 10:
                                await save_chat_log(chat_messages, str(ages2[0]))
                            
                            continue  # Начинаем новый цикл
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
