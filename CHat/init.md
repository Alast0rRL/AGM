# Nekto.me Chat Bot — Init

## Запуск

```powershell
cd CHat
pip install -r requirements.txt
playwright install chromium
copy .env.example .env    # отредактировать USER_DATA_DIR
.\start-chrome.bat        # убивает ВСЕ chrome.exe, запускает на порту 9222
python bot.py             # или: py bot.py (через run.bat)
```

## Структура проекта

```
CHat/
  bot.py              — ВСЯ логика бота (~1370 строк, единственный entrypoint)
  config.py           — env конфиг (USER_DATA_DIR, REMOTE_DEBUGGING_PORT)
  test_bot.py         — 133 юнит-теста на чистую логику
  CHANGELOG.md        — история изменений
  init.md             — этот файл
  voices/             — ONNX голоса для Piper TTS
  chat_logs/          — логи чатов (относительно CWD)
  start-chrome.bat    — запуск Chrome с remote-debugging
  run.bat             — просто py bot.py
  requirements.txt    — зависимости
```

**Неиспользуемые файлы** (старые драфты, bot.py их не импортирует):
- `brain.py`, `observer.py`, `executor.py` — OOP-модули из старого дизайна

## Архитектура

3-stage pipeline. Каждый stage — async функция, возвращает `count` (успех) или `None` (завершить чат):

```python
stages = [stage_greeting, stage_names, stage_free_chat]
for stage_fn in stages:
    result = await stage_fn(page, count, chat_messages, state)
    if result is None:
        break
    count = result
```

### Stage 1: `stage_greeting()`
- Отправляет "привет"
- Спрашивает "сколько лет"
- Валидирует возраст в `[17, 18, 19]`
- Обрабатывает разные типы ответов: вопросы, представления, "а ты?", "как дела" и т.д.

### Stage 2: `stage_names()`
- Ждёт до 20 секунд первого сообщения партнёра
- Если спрашивают возраст/а тебе → отвечает "19", потом "Максим, тебя?"
- Если представляются или спрашивают имя → "Максим" или "Максим, тебя?"
- Таймаут → "Максим, тебя?" проактивно
- Ждёт до 15 секунд ответ на имя

### Stage 3: `stage_free_chat()`
- Бесконечный цикл: отвечает на вопросы
- Триггеры: имя, откуда, приятно познакомиться, возраст, "а ты?", "как дела", "что делаешь"
- Фильтры: украинский, мусульманская лексика, грубость, несовершеннолетние

### `ChatState` dataclass
```python
@dataclass
class ChatState:
    partner_name: str = None
    partner_age: str = None
    said_19: bool = False
    name_sent: bool = False
    stage: int = 1
```

## Паттерны

Паттерны — **подстрочные** (`if p in t.lower()`), не regex:
- `AGE_ASK_PATTERNS` — вопросы возраста (включая опечатки: "скока", "скилко", "тибе")
- `NAME_ASK_PATTERNS` — вопросы имени
- `AND_YOU_PATTERNS` — "а ты?", "тебе?", "тебя?"
- `FROM_ASK_PATTERNS` — "откуда", "город"
- `HOW_ARE_YOU_PATTERNS` — "как дела"
- `WHAT_ARE_YOU_DOING_PATTERNS` — "что делаешь"
- `NICE_TO_MEET_PATTERNS` — "приятно познакомиться"
- `COMPLIMENT_PATTERNS` — комплименты имени

**Короткие подстроки опасны!** "да" в "откуда", "тебя" в "тебя любят". Всегда проверяй граничные случаи.

## Фильтры

| Функция | Что ловит |
|---------|-----------|
| `is_ukrainian()` | "привiт", "тобi", признание "я украинка" (НЕ вопрос "ты украинец?") |
| `is_muslim()` | "ассалам", "машаллах", "иншаллах" и т.д. |
| `is_dismissive()` | "молчи", "заткнись", "пошел нах", "занята" и т.д. |
| `is_underage()` | "мне 15", "мне нет 18", числа < 17 в начале текста |

## Персона бота

- Имя: **Максим** (хардкод)
- Возраст: **19** (хардкод)
- Проверка пола: `_partner_name_received()` — если партнёр уже назвал имя, отвечаем "Максим" без вопроса обратно

## Тесты

```powershell
cd CHat
$env:PYTHONIOENCODING='utf-8'; python test_bot.py
```

133 теста на чистую логику: паттерны, фильтры, хелперы. **Все тесты должны проходить до и после каждого изменения bot.py.** Если тест упал — откат.

## Протокол работы

1. **Коммит перед изменением** — `git commit` текущего состояния
2. **Целевое изменение** — делать ровно то, что нужно, не трогать остальное
3. **Согласование** — показать план изменений → ты одобряешь → делаю
4. **Тесты** — `python test_bot.py`, все 133 должны пройти
5. **Changelog** — записать в `CHat/CHANGELOG.md`
6. **Не переписывать** — редактировать существующий код, не писать заново

## Баги (известные)

- `start-chrome.bat` убивает ВСЕ chrome.exe — закрыть все браузеры заранее
- Два экземпляра Chrome — `start-chrome.bat` + `bot.py` могут конфликтовать по порту/профилю
- `winsound` — только Windows
- `DEBUG = True` захардкожен — весь debug идёт в stdout
- `wait_for_partner_msg` при таймауте возвращает `0` вместо реального времени

## Селекторы (в bot.py, строки 84–94)

```python
START_BUTTON = "#searchCompanyBtn"
ACCEPT_RULES = ".swal2-confirm"
INPUT_FIELD = ".emojionearea-editor"
MESSAGES = ".window_chat_dialog_text"
STOP_BUTTON = "button:has-text('Завершить'), .btn-stop, ..."
CONFIRM_STOP = ".swal2-confirm"
NEW_CHAT_BUTTON = "button:has-text('Начать новый чат')"
```

`config.py` имеет `SELECTORS` dict, но bot.py его не использует — все селекторы хардкодены.
