# AGM — Nekto.me chat automator

Playwright-бот (Python) ведёт чаты на nekto.me: здоровается, спрашивает возраст, представляется «Максимом» (19 лет) и поддерживает свободный диалог с помощью шаблонов и эвристик. **Только Windows.**

## Установка

```powershell
pip install -r requirements.txt
playwright install chromium
copy .env.example .env    # впиши свой USER_DATA_DIR
```

## Запуск

```powershell
.\start-chrome.bat   # убивает ВСЕ chrome.exe, запускает Chrome на порту 9222
python bot.py        # или: run.bat
```

Управление во время работы:

- **`S`** — пометить текущий диалог как удачный (сохранится в `chat_logs/success/`)
- **`Ctrl+C`** — остановить бота

## Как это работает

Бот — конвейер из 3 стадий (`bot.py`):

1. **`stage_greeting`** — «привет», вопрос «сколько лет», валидация возраста `[17, 18, 19]`
2. **`stage_names`** — обмен именами: «Максим, тебя?», ответ «19» на «а тебе?»
3. **`stage_free_chat`** — бесконечный диалог: ответы на вопросы, реакция на грубость/украинский/мусульманскую лексику

Паттерны — подстроки, а не regex; учитывают опечатки. Текст настраивается константами в начале `bot.py`.

Опционально: TTS-озвучка (Piper + модели в `voices/`).

## Логирование

Сохраняются **только удачные диалоги**:

- вручную — клавиша `S` в консоли (outcome `manual`)
- автоматически — чат длиннее `SUCCESS_MIN_MSGS` сообщений И дольше `SUCCESS_MIN_SEC` секунд (outcome `auto`)

Удачные диалоги попадают в `chat_logs/success/`, сводка — в `chat_logs/summary.csv`. Папка в `.gitignore`.

## Тесты

```powershell
$env:PYTHONIOENCODING='utf-8'; python test_bot.py
```

650+ юнит-тестов чистой логики (паттерны, фильтры, хелперы).

## Структура

| Файл | Роль |
|---|---|
| `bot.py` | Весь бот (~2270 строк): стадии, паттерны, TTS |
| `config.py` | `.env` → `USER_DATA_DIR`, `REMOTE_DEBUGGING_PORT` |
| `test_bot.py` | Юнит-тесты |
| `voices/` | ONNX-модели Piper для TTS |
| `chat_logs/` | Логи удачных диалогов (runtime, gitignored) |
| `run.bat`, `start-chrome.bat` | Запуск |
