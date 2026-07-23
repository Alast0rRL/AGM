"""
Тесты поведения бота — проверяют чистую логику без Playwright.
Запуск: python test_bot.py (или pytest test_bot.py)
"""
import sys
import os

# Импортируем функции из bot.py
from bot import (
    is_age_question, is_self_introduction, is_ukrainian, is_muslim,
    is_dismissive, is_underage, is_confirmation_question,
    _name_already_sent, _already_sent_19, _partner_name_received,
    check_filters, ChatState,
    AGE_ASK_PATTERNS, NAME_ASK_PATTERNS, AND_YOU_PATTERNS,
    FROM_ASK_PATTERNS, HOW_ARE_YOU_PATTERNS, WHAT_ARE_YOU_DOING_PATTERNS,
    NICE_TO_MEET_PATTERNS, COMPLIMENT_PATTERNS,
)

passed = 0
failed = 0

def assert_eq(name, actual, expected):
    global passed, failed
    if actual == expected:
        passed += 1
    else:
        failed += 1
        print(f"  FAIL: {name}")
        print(f"    expected: {expected}")
        print(f"    actual:   {actual}")

def assert_true(name, val):
    assert_eq(name, val, True)

def assert_false(name, val):
    assert_eq(name, val, False)

# ===== is_age_question =====
print("\n=== is_age_question ===")
assert_true("сколько тебе", is_age_question("сколько тебе лет?"))
assert_true("а тебе сколько", is_age_question("а тебе сколько"))
assert_true("тебе сколько", is_age_question("тебе сколько?"))
assert_true("сколько лет", is_age_question("сколько лет"))
assert_true("твой возраст", is_age_question("твой возраст?"))
assert_true("скока", is_age_question("скока тебе"))
assert_true("скоко", is_age_question("скоко лет"))
assert_true("сколька", is_age_question("сколька"))
assert_true("скилко опечатка", is_age_question("скилко"))
assert_true("тибе опечатка", is_age_question("а тибе"))
assert_true("тибя опечатка", is_age_question("а тибя"))
assert_true("теюе опечатка", is_age_question("теюе"))
assert_true("вам сколько", is_age_question("вам сколько лет"))
assert_false("пустой текст", is_age_question(""))
assert_false("None", is_age_question(None))
assert_false("привет не возраст", is_age_question("привет как дела"))
assert_false("обычный текст", is_age_question("я сегодня ходила в магазин"))
assert_true("сколик", is_age_question("сколик"))
assert_true("колко", is_age_question("колко"))
assert_true("атебе", is_age_question("атебе"))
assert_false("те? не возраст а and_you", is_age_question("те?"))
assert_true("самой", is_age_question("а самой?"))
assert_true("самому", is_age_question("а самому?"))
assert_false("а тебе 19 не возраст", is_age_question("а тебе 19?"))

# ===== is_self_introduction =====
print("\n=== is_self_introduction ===")
assert_true("меня зовут Света", is_self_introduction("Меня зовут Света"))
assert_true("зови меня Лена", is_self_introduction("Зови меня Лена"))
assert_true("я Света", is_self_introduction("Я Света"))
assert_true("привет я Эльвина 19", is_self_introduction("Привет я Эльвина 19"))
assert_true("йо я Аня", is_self_introduction("Йо я Аня"))
assert_true("салам я Мария", is_self_introduction("Салам я Мария"))
assert_true("привет я Катя 18", is_self_introduction("Привет я Катя 18"))
assert_true("хай я Даша", is_self_introduction("Хай я Даша"))
assert_false("пустой", is_self_introduction(""))
assert_false("None", is_self_introduction(None))
assert_false("обычный текст", is_self_introduction("я люблю кофе"))
assert_false("глагол после я", is_self_introduction("я люблю"))
assert_false("я делаю", is_self_introduction("я делаю уроки"))
assert_true("я Оля", is_self_introduction("я Оля"))
assert_true("я Марина 19", is_self_introduction("я Марина 19"))
assert_true("я Алина", is_self_introduction("я Алина"))

# ===== is_ukrainian =====
print("\n=== is_ukrainian ===")
assert_true("привiт", is_ukrainian("привiт"))
assert_true("привіт", is_ukrainian("привіт"))
assert_true("тобi", is_ukrainian("тобi"))
assert_true("тобі", is_ukrainian("тобі"))
assert_true("украинка", is_ukrainian("я украинка"))
assert_true("украинец", is_ukrainian("я украинец"))
assert_false("пустой", is_ukrainian(""))
assert_false("None", is_ukrainian(None))
assert_false("привет русский", is_ukrainian("привет как дела"))
assert_false("ты украинец? вопрос", is_ukrainian("ты украинец?"))

# ===== is_muslim =====
print("\n=== is_muslim ===")
assert_true("ассалам", is_muslim("ассалам алейкум"))
assert_true("алейкум", is_muslim("алейкум"))
assert_true("машаллах", is_muslim("машаллах"))
assert_true("ин ша аллах", is_muslim("ин ша аллах"))
assert_true("иншаллах", is_muslim("иншаллах"))
assert_true("бисмилля", is_muslim("бисмилля"))
assert_true("мусульманин", is_muslim("я мусульманин"))
assert_true("харом", is_muslim("харом"))
assert_true("халаль", is_muslim("халаль"))
assert_false("пустой", is_muslim(""))
assert_false("None", is_muslim(None))
assert_false("обычный текст", is_muslim("привет как дела"))

# ===== is_dismissive =====
print("\n=== is_dismissive ===")
assert_true("молчи", is_dismissive("молчи"))
assert_true("заткнись", is_dismissive("заткнись"))
assert_true("пошел нах", is_dismissive("пошел нахуй"))
assert_true("иди отсюда", is_dismissive("иди отсюда"))
assert_true("не хочу", is_dismissive("не хочу общаться"))
assert_true("занята", is_dismissive("я занята"))
assert_true("задолбал", is_dismissive("задолбал"))
assert_true("тупой", is_dismissive("ты тупой"))
assert_false("пустой", is_dismissive(""))
assert_false("None", is_dismissive(None))
assert_true("занята в предложении", is_dismissive("я сейчас занята делами"))

# ===== is_underage =====
print("\n=== is_underage ===")
assert_true("мне 15", is_underage("мне 15"))
assert_true("мне 12", is_underage("мне 12 лет"))
assert_true("мне 16", is_underage("мне 16"))
assert_true("мне 17", is_underage("мне 17"))
assert_true("мне нет 18", is_underage("мне нет 18"))
assert_true("несовершеннолетняя", is_underage("я несовершеннолетняя"))
assert_true("14 я маленькая", is_underage("14 я маленькая"))
assert_true("мне семнадцать", is_underage("мне семнадцать"))
assert_true("мне шестнадцать", is_underage("мне шестнадцать"))
assert_true("мне пятнадцать", is_underage("мне пятнадцать"))
assert_false("пустой", is_underage(""))
assert_false("None", is_underage(None))
assert_false("мне 18", is_underage("мне 18"))
assert_false("мне 19", is_underage("мне 19"))
assert_false("мне 25", is_underage("мне 25 лет"))
assert_false("мне 20", is_underage("мне 20"))

# ===== is_confirmation_question =====
print("\n=== is_confirmation_question ===")
assert_true("а ты русский да", is_confirmation_question("а ты русский да"))
assert_true("а ты русская да?", is_confirmation_question("а ты русская да?"))
assert_true("а ты русский ага", is_confirmation_question("а ты русский ага"))
assert_true("а ты русская верно", is_confirmation_question("а ты русская верно"))
assert_false("просто а ты", is_confirmation_question("а ты откуда"))
assert_false("а ты 19", is_confirmation_question("а ты 19"))
assert_false("пустой", is_confirmation_question(""))

# ===== _name_already_sent =====
print("\n=== _name_already_sent ===")
assert_true("имя в сообщениях", _name_already_sent([{"role": "own", "content": "Максим, тебя?"}]))
assert_true("имя маленькими", _name_already_sent([{"role": "own", "content": "максим"}]))
assert_false("нет имени", _name_already_sent([{"role": "own", "content": "привет"}]))
assert_false("пустой список", _name_already_sent([]))
assert_true("имя в контенте", _name_already_sent([{"role": "own", "content": "Я Максим 19"}]))

# ===== _already_sent_19 =====
print("\n=== _already_sent_19 ===")
assert_true("19 отправлено", _already_sent_19([{"role": "own", "content": "19"}]))
assert_true("19 с пробелами", _already_sent_19([{"role": "own", "content": " 19 "}]))
assert_false("нет 19", _already_sent_19([{"role": "own", "content": "привет"}]))
assert_false("19 от другого", _already_sent_19([{"role": "other", "content": "19"}]))
assert_false("пустой список", _already_sent_19([]))
assert_false("девятнадцать текстом", _already_sent_19([{"role": "own", "content": "девятнадцать"}]))

# ===== _partner_name_received =====
print("\n=== _partner_name_received ===")
assert_true("самопрезентация", _partner_name_received([{"role": "other", "content": "Я Света"}]))
assert_true("одно слово имя", _partner_name_received([{"role": "other", "content": "Света"}]))
assert_false("нет имени", _partner_name_received([{"role": "other", "content": "привет"}]))
assert_false("свои сообщения", _partner_name_received([{"role": "own", "content": "Я Максим"}]))
assert_false("пустой список", _partner_name_received([]))
assert_false("не имя крутой", _partner_name_received([{"role": "other", "content": "круто"}]))
assert_false("не имя ладно", _partner_name_received([{"role": "other", "content": "ладно"}]))
assert_true("меня зовут Оля", _partner_name_received([{"role": "other", "content": "Меня зовут Оля"}]))
assert_true("зови меня Лена", _partner_name_received([{"role": "other", "content": "Зови меня Лена"}]))
assert_false("привет имя", _partner_name_received([{"role": "other", "content": "Привет"}]))
assert_false("спасибо не имя", _partner_name_received([{"role": "other", "content": "Спасибо"}]))
assert_false("ага не имя", _partner_name_received([{"role": "other", "content": "ага"}]))

# ===== check_filters =====
print("\n=== check_filters ===")
assert_eq("украинский", check_filters("привiт"), "украинский язык")
assert_eq("мусульманская лексика", check_filters("ассалам алейкум"), "мусульманская лексика")
assert_eq("грубость", check_filters("молчи"), "грубость/отказ")
assert_eq("несовершеннолетняя", check_filters("мне 15"), "несовершеннолетняя")
assert_eq("нормальный текст", check_filters("привет как дела"), None)
assert_eq("пустой текст", check_filters(""), None)

# ===== Частичные совпадения (проверяем что короткие подстроки не ломают) =====
print("\n=== Граничные случаи ===")
assert_false("'тебя' в длинном предложении", is_age_question("тебя любят?"))
assert_false("'сколько' без тебя", is_age_question("сколько их было"))
assert_true("сколько тебя", is_age_question("сколько тебя лет"))

# ===== ChatState =====
print("\n=== ChatState ===")
state = ChatState()
assert_eq("default partner_name", state.partner_name, None)
assert_eq("default partner_age", state.partner_age, None)
assert_eq("default said_19", state.said_19, False)
assert_eq("default name_sent", state.name_sent, False)
assert_eq("default stage", state.stage, 1)

# ===== Резюме =====
print(f"\n{'='*40}")
print(f"Результат: {passed} OK, {failed} FAIL")
if failed > 0:
    print("ЕСТЬ ОШИБКИ!")
    sys.exit(1)
else:
    print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
