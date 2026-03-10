import asyncio
import re
import random
import winsound
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

async def wait_for_partner_msg(page, last_count):
    """Ждет нового сообщения от собеседника"""
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
            return text, len(current_msgs)
        await asyncio.sleep(0.2)  # Уменьшили интервал опроса с 0.5 до 0.2 секунды

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

                # 4. Пишем "привет" - сразу без задержки
                await human_type(page, "привет")
                count += 1 # Наше сообщение

                # 5. Ждем ответ
                print("Ждем ответ на 'привет'...")
                resp, count = await wait_for_partner_msg(page, count)

                # Если чат завершен во время ожидания
                if resp is None:
                    print("Чат завершен собеседником. Начинаю новый...")
                    continue

                # 6. Пишем "сколько лет" - сразу без задержки
                await human_type(page, "сколько лет")
                count += 1

                # 7. Ждем ответ про возраст
                print("Ждем возраст...")
                age_text, count = await wait_for_partner_msg(page, count)

                # Если чат завершен во время ожидания
                if age_text is None:
                    print("Чат завершен собеседником. Начинаю новый...")
                    continue

                print(f"Собеседник ответил: {age_text}")

                # 8. Проверка возраста (17, 18, 19)
                ages = [int(s) for s in re.findall(r'\d+', age_text)]
                target_ages = [17, 18, 19]

                is_target = any(a in target_ages for a in ages)

                if is_target:
                    print(f"ПОДХОДИТ ({ages})! Отправляю 'неужели' и останавливаю бота.")
                    # Воспроизводим звуковой сигнал (громкий и длинный)
                    winsound.Beep(1000, 1000)  # Частота 1000 Гц, длительность 1000 мс
                    await asyncio.sleep(0.2)
                    winsound.Beep(1000, 1000)  # Второй сигнал
                    await human_type(page, "неужели")
                    await asyncio.sleep(0.5)
                    await human_type(page, "Небольшой тест")
                    await asyncio.sleep(0.5)
                    await human_type(page, "Любимый мультик детства??")
                    
                    # Ждём немного и проверяем, не завершен ли чат
                    await asyncio.sleep(2)
                    new_chat_btn = await page.query_selector(NEW_CHAT_BUTTON)
                    if new_chat_btn:
                        is_visible = await new_chat_btn.is_visible()
                        if is_visible:
                            print("Чат завершен собеседником. Начинаю новый...")
                            continue
                    
                    input("Нажми Enter в консоли, чтобы снова запустить бота...")
                else:
                    # Возраст не назван или не подходит - переспрашиваем или уточняем
                    print(f"Возраст не назван или не подходит: '{age_text}' (найдено: {ages})")

                    # Проверяем, есть ли в ответе числа (возможно возраст в другом формате)
                    if ages:
                        # Возраст есть, но не 17-19
                        print("Возраст не подходит (не 17-19). Завершаю чат.")
                        await end_chat(page)
                    else:
                        # Возраст не назван - переспрашиваем сразу
                        print("Переспрашиваем возраст...")
                        await asyncio.sleep(3)  # Задержка перед повторным вопросом
                        await human_type(page, "ну скажи сколько лет?")
                        count += 1

                        # Ждем ответ ещё раз
                        print("Ждем возраст (повторно)...")
                        age_text2, count = await wait_for_partner_msg(page, count)

                        if age_text2 is None:
                            print("Чат завершен собеседником. Начинаю новый...")
                            continue

                        
                        print(f"Собеседник ответил: {age_text2}")
                        ages2 = [int(s) for s in re.findall(r'\d+', age_text2)]
                        is_target2 = any(a in target_ages for a in ages2)
                        
                        if is_target2:
                            print(f"ПОДХОДИТ ({ages2})! Останавливаю бота для ручного общения.")
                            input("Нажми Enter в консоли, чтобы снова запустить бота...")
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
