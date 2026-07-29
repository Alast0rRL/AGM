"""
Тесты поведения бота — проверяют чистую логику без Playwright.
Запуск: python test_bot.py (или pytest test_bot.py)
"""
import sys
import os
import tempfile
import asyncio

# Импортируем функции из bot.py
from bot import (
    is_age_question, is_self_introduction, is_ukrainian, is_muslim,
    is_dismissive, is_underage, is_confirmation_question,
    _name_already_sent, _already_sent_19, _partner_name_received,
    _extract_name_first_word,
    check_filters, ChatState, _can_send, save_chat_log,
    AGE_ASK_PATTERNS, NAME_ASK_PATTERNS, AND_YOU_PATTERNS,
    FROM_ASK_PATTERNS, HOW_ARE_YOU_PATTERNS, WHAT_ARE_YOU_DOING_PATTERNS,
    NICE_TO_MEET_PATTERNS, COMPLIMENT_PATTERNS, LOOKING_FOR_PATTERNS,
    RUSSIAN_CONFIRM_PATTERNS, RUSSIAN_DENY_PATTERNS,
    ZOVUT_PATTERNS, TG_CONTINUE_PATTERNS,
    _SHORT_AND_YOU, _GREETINGS, _NOT_NAMES,
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
assert_false("тебе ? с пробелом не возраст", is_age_question("тебе ?"))

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
# Вопросы о мусульманах не триггерят
assert_false("вопрос о мусульманках", is_muslim("А что с мусульманками не так?"))
assert_false("вопрос про мусульман", is_muslim("почему мусульмане так делают?"))
# Самоидентификация с вопросом всё ещё триггерит
assert_true("я мусульманка а ты", is_muslim("я мусульманка, а ты?"))
assert_true("я мусульманин", is_muslim("я мусульманин"))

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
assert_false("мне 17", is_underage("мне 17"))
assert_true("мне нет 18", is_underage("мне нет 18"))
assert_true("несовершеннолетняя", is_underage("я несовершеннолетняя"))
assert_true("14 я маленькая", is_underage("14 я маленькая"))
assert_false("мне семнадцать", is_underage("мне семнадцать"))
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
assert_false("нормас не имя", _partner_name_received([{"role": "other", "content": "нормас"}]))
assert_false("норма не имя", _partner_name_received([{"role": "other", "content": "норма"}]))
assert_false("нормально не имя", _partner_name_received([{"role": "other", "content": "нормально"}]))
assert_true("имя с маленькой буквы", _partner_name_received([{"role": "other", "content": "катя"}]))
assert_true("вика маленькими", _partner_name_received([{"role": "other", "content": "вика"}]))
assert_true("аня маленькими", _partner_name_received([{"role": "other", "content": "аня"}]))

# ===== FROM_ASK_PATTERNS =====
print("\n=== FROM_ASK_PATTERNS ===")
def _from_ask(t):
    return any(p in t.lower() for p in FROM_ASK_PATTERNS)
assert_true("ты откуда", _from_ask("ты откуда?"))
assert_true("откуда ты", _from_ask("откуда ты"))
assert_true("где живешь", _from_ask("где ты живешь?"))
assert_true("из какого города", _from_ask("из какого ты города?"))
assert_true("с какого города", _from_ask("с какого города?"))
assert_true("в каком городе", _from_ask("в каком городе ты живешь?"))
assert_true("какой город", _from_ask("какой город?"))
assert_false("город в контексте", _from_ask("город Москва"))
assert_false("просто привет", _from_ask("привет"))
assert_false("без темы", _from_ask("я люблю кофе"))

# откуда + знаешь exclusion (not a location question)
def _from_ask_excluded(t):
    tl = t.lower()
    return any(p in tl for p in FROM_ASK_PATTERNS) and not ("откуда" in tl and "знаешь" in tl)
assert_true("откуда ты", _from_ask_excluded("откуда ты?"))
assert_true("ты откуда", _from_ask_excluded("ты откуда?"))
assert_false("откуда знаешь", _from_ask_excluded("да откуда ты знаешь"))
assert_false("откуда это знаешь", _from_ask_excluded("откуда ты это знаешь?"))
assert_false("а откуда знаешь", _from_ask_excluded("а откуда ты знаешь?"))
assert_true("знаешь без откуда", _from_ask_excluded("где ты живешь?"))
assert_true("откуда без знаешь", _from_ask_excluded("откуда вы?"))

# ===== NICE_TO_MEET_PATTERNS =====
print("\n=== NICE_TO_MEET_PATTERNS ===")
def _nice(t):
    return any(p in t.lower() for p in NICE_TO_MEET_PATTERNS)
assert_true("приятно познакомиться", _nice("приятно познакомиться"))
assert_true("приятно коротко", _nice("приятно"))
assert_true("очень приятно", _nice("очень приятно"))
assert_true("рада знакомству", _nice("рада знакомству"))
assert_true("рад знакомству", _nice("рад знакомству"))
assert_true("приятно знакомиться", _nice("приятно знакомиться"))
assert_true("познакомится опечатка", _nice("приятно познакомится"))
assert_false("просто привет", _nice("привет"))
# "приятно" — подстрока "неприятно", это известное ограничение
assert_true("неприятно содержит приятно", _nice("это неприятно"))

# ===== WHAT_ARE_YOU_DOING_PATTERNS =====
print("\n=== WHAT_ARE_YOU_DOING_PATTERNS ===")
def _doing(t):
    return any(p in t.lower() for p in WHAT_ARE_YOU_DOING_PATTERNS)
assert_true("что делаешь", _doing("что делаешь?"))
assert_true("чем занят", _doing("чем занят?"))
assert_true("чем занимаешься", _doing("чем занимаешься?"))
assert_true("что сейчас делаешь", _doing("что сейчас делаешь?"))
assert_true("чем шумишь", _doing("чем шумишь"))
assert_false("просто привет", _doing("привет"))
assert_false("прошедшее время", _doing("что делал вчера"))
assert_false("обратный порядок", _doing("занят чем?"))

# ===== HOW_ARE_YOU_PATTERNS =====
print("\n=== HOW_ARE_YOU_PATTERNS ===")
def _how(t):
    return any(p in t.lower() for p in HOW_ARE_YOU_PATTERNS)
assert_true("как дела", _how("как дела?"))
assert_true("как твои дела", _how("как твои дела"))
assert_true("как сам", _how("как сам?"))
assert_true("как сама", _how("как сама?"))
assert_true("как жизнь", _how("как жизнь?"))
assert_true("что нового", _how("что нового?"))
assert_true("как поживаешь", _how("как поживаешь?"))
assert_true("как оно", _how("как оно"))
assert_true("как там", _how("как там"))
assert_true("норм", _how("норм?"))
assert_true("норм без вопроса", _how("ну норм"))
assert_false("просто привет", _how("привет"))
assert_false("дело не дела", _how("дело в том"))

# ===== COMPLIMENT_PATTERNS =====
print("\n=== COMPLIMENT_PATTERNS ===")
def _compliment(t):
    return any(p in t.lower() for p in COMPLIMENT_PATTERNS)
assert_true("красивое имя", _compliment("красивое имя"))
assert_true("крутое имя", _compliment("крутое имя"))
assert_true("хорошее имя", _compliment("хорошее имя"))
assert_true("прикольное имя", _compliment("прикольное имя"))
assert_true("милое имя", _compliment("милое имя"))
assert_true("какое имя", _compliment("какое имя"))
assert_true("имя крутое", _compliment("имя крутое"))
assert_true("имя красивое", _compliment("имя красивое"))
assert_true("классное имя", _compliment("классное имя"))
assert_true("интересное имя", _compliment("интересное имя"))
# стрange имя — так в оригинальном коде (опечатка)
assert_true("стрange имя", _compliment("стрange имя"))
assert_false("просто привет", _compliment("привет"))
assert_false("без имени", _compliment("тебя зовут"))

# ===== LOOKING_FOR_PATTERNS =====
print("\n=== LOOKING_FOR_PATTERNS ===")
def _looking(t):
    return any(p in t.lower() for p in LOOKING_FOR_PATTERNS)
assert_true("что ищешь", _looking("что ищешь?"))
assert_true("что ищешь тут", _looking("что ищешь тут?"))
assert_true("кого ищешь", _looking("кого ищешь?"))
assert_false("просто привет", _looking("привет"))
assert_false("без вопроса", _looking("ищу человека"))
# "кого ты ищешь" не ловится — "кого ищешь" не подстрока "кого ты ищешь"
assert_false("кого ты ищешь", _looking("кого ты ищешь?"))

# ===== AND_YOU_PATTERNS (ложные срабатывания) =====
print("\n=== AND_YOU_PATTERNS (ложные срабатывания) ===")
def _and_you(t):
    return any(p in t.lower() for p in AND_YOU_PATTERNS)
# "тебе" без знака вопроса больше не в списке — не должно срабатывать
assert_false("я тебе напишу", _and_you("Я тебе напишу"))
assert_false("я тебя люблю", _and_you("я тебя люблю"))
assert_false("тебе не стыдно", _and_you("тебе не стыдно"))
# А эти должны — настоящие встречные вопросы
assert_true("а тебе с вопросом", _and_you("а тебе?"))
assert_true("а тебе 19", _and_you("а тебе 19"))
assert_true("тебе? коротко", _and_you("тебе?"))
assert_true("тебе ? с пробелом", _and_you("тебе ?"))
assert_true("тебя ? с пробелом", _and_you("тебя ?"))
assert_true("вам ? с пробелом", _and_you("вам ?"))
assert_true("вас ? с пробелом", _and_you("вас ?"))
assert_true("а ты", _and_you("а ты"))

# ===== NAME_ASK_PATTERNS (ложные срабатывания) =====
print("\n=== NAME_ASK_PATTERNS (ложные срабатывания) ===")
def _name_ask(t):
    return any(p in t.lower() for p in NAME_ASK_PATTERNS)
# "имя" без знака вопроса больше не в списке — не должно срабатывать
assert_false("красивое имя", _name_ask("красивое имя"))
assert_false("у меня красивое имя", _name_ask("у меня красивое имя"))
assert_false("просто имя", _name_ask("просто имя"))
# А эти должны — настоящие вопросы про имя
assert_true("как тебя зовут", _name_ask("как тебя зовут?"))
assert_true("твое имя", _name_ask("твое имя"))
assert_true("а тебя", _name_ask("а тебя?"))
assert_true("имя? с вопросом", _name_ask("имя?"))
assert_true("имя ? с пробелом", _name_ask("имя ?"))
assert_true("тебя ? с пробелом", _name_ask("тебя ?"))
assert_true("как имя? с вопросом", _name_ask("как имя?"))
assert_true("как вас зовут", _name_ask("как вас зовут?"))
assert_true("вас зовут", _name_ask("вас зовут?"))
assert_true("как вас кратко", _name_ask("как вас?"))
assert_true("а как вас", _name_ask("а как вас?"))
assert_true("вас? с вопросом", _name_ask("вас?"))
assert_true("вас ? с пробелом", _name_ask("вас ?"))
assert_true("а вас?", _name_ask("а вас?"))
assert_true("а вас ?", _name_ask("а вас ?"))
assert_false("вас это не касается", _name_ask("вас это не касается"))
assert_true("как зовут тебя", _name_ask("как зовут тебя?"))
assert_true("зовут тебя", _name_ask("зовут тебя?"))
assert_false("меня зовут аня", _name_ask("меня зовут аня"))

# ===== RUSSIAN_CONFIRM_PATTERNS =====
print("\n=== RUSSIAN_CONFIRM_PATTERNS ===")
def _rus_confirm(t):
    return any(p in t.lower() for p in RUSSIAN_CONFIRM_PATTERNS)
assert_true("да", _rus_confirm("да"))
assert_true("ага", _rus_confirm("ага"))
assert_false("русская без да", _rus_confirm("русская"))
assert_true("да русская", _rus_confirm("да русская"))
assert_true("да, русская", _rus_confirm("да, русская"))
assert_true("конечно", _rus_confirm("конечно"))
assert_true("да конечно", _rus_confirm("да конечно"))
assert_true("да, конечно", _rus_confirm("да, конечно"))
assert_false("нет", _rus_confirm("нет"))
assert_false("не русская", _rus_confirm("не русская"))
assert_false("привет", _rus_confirm("привет"))

# ===== ZOVUT_PATTERNS =====
print("\n=== ZOVUT_PATTERNS ===")
def _zovut(t):
    return any(p in t.lower() for p in ZOVUT_PATTERNS)
assert_true("зовут? с вопросом", _zovut("зовут?"))
assert_true("а зовут? с префиксом", _zovut("а зовут?"))
assert_true("как зовут? полный", _zovut("как зовут?"))
assert_false("зовут без вопроса", _zovut("зовут"))
assert_false("меня зовут", _zovut("меня зовут аня"))
assert_false("пустая строка", _zovut(""))

# ===== RUSSIAN_DENY_PATTERNS =====
print("\n=== RUSSIAN_DENY_PATTERNS ===")
def _rus_deny(t):
    return any(p in t.lower() for p in RUSSIAN_DENY_PATTERNS)
assert_true("нет", _rus_deny("нет"))
assert_true("неа", _rus_deny("неа"))
assert_true("не русская", _rus_deny("не русская"))
assert_true("татарка", _rus_deny("татарка"))
assert_true("армянка", _rus_deny("армянка"))
assert_true("азербайджанка", _rus_deny("азербайджанка"))
assert_false("да", _rus_deny("да"))
assert_false("ага", _rus_deny("ага"))
assert_false("конечно", _rus_deny("конечно"))
assert_false("привет", _rus_deny("привет"))

# ===== TG_CONTINUE_PATTERNS =====
print("\n=== TG_CONTINUE_PATTERNS ===")
def _tg(t):
    return any(p in t.lower() for p in TG_CONTINUE_PATTERNS)
assert_true("в тг", _tg("давай в тг"))
assert_true("в телеграм", _tg("скинь в телеграм"))
assert_true("продолжить в тг", _tg("хочешь продолжить в тг?"))
assert_true("тг коротко", _tg("тг?"))
assert_true("ссылку", _tg("скинь ссылку"))
assert_true("свой тг", _tg("напиши свой тг"))
assert_true("дай тг", _tg("дай тг"))
assert_false("привет", _tg("привет"))
assert_false("без темы", _tg("я люблю кофе"))

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

# Дополнительные граничные случаи для is_age_question
assert_true("сколька тебе", is_age_question("сколька тебе?"))
assert_true("сколко тебе", is_age_question("сколко тебе?"))
assert_true("а тибе 19 через пробел", is_age_question("а тибе 19"))
assert_true("а тибя 18", is_age_question("а тибя 18"))

# Дополнительные граничные случаи для is_self_introduction
assert_true("привет Вика", is_self_introduction("привет Вика"))
assert_true("приветик я Маша", is_self_introduction("приветик я Маша"))
assert_false("я не представилась", is_self_introduction("я очень рада"))
assert_false("одно слово не имя", is_self_introduction("прикольно"))
assert_false("я решила", is_self_introduction("я решила написать"))

# Дополнительные граничные случаи для is_underage
assert_true("мне 10", is_underage("мне 10"))
assert_true("мне 11", is_underage("мне 11"))
assert_true("мне 13", is_underage("мне 13"))
assert_true("мне четырнадцать", is_underage("мне четырнадцать"))
assert_false("17 лет с пробелом", is_underage("17 лет"))
assert_false("17 я взрослая", is_underage("17 я взрослая"))
assert_false("7 лучше не возраст", is_underage("7 лучше"))
assert_true("10 лет спереди", is_underage("10 лет я маленькая"))

# Дополнительные граничные случаи для is_dismissive
assert_true("пошёл нах", is_dismissive("пошёл нах"))
assert_true("закройся", is_dismissive("закройся"))
assert_true("отстань", is_dismissive("отстань"))
assert_true("надоела", is_dismissive("ты надоела"))
assert_true("некогда", is_dismissive("мне некогда"))
assert_true("занят", is_dismissive("я занят"))
assert_true("нет времени", is_dismissive("у меня нет времени"))
assert_true("иди нах", is_dismissive("иди нахуй"))
assert_false("просто привет", is_dismissive("привет как дела"))

# Дополнительные граничные случаи для _partner_name_received
assert_true("Макс короткое", _partner_name_received([{"role": "other", "content": "Макс"}]))
assert_false("своё сообщение Максим", _partner_name_received([{"role": "own", "content": "Я Максим"}]))
assert_false("нормально не имя", _partner_name_received([{"role": "other", "content": "нормально"}]))
assert_false("конечно не имя", _partner_name_received([{"role": "other", "content": "конечно"}]))
assert_false("ок не имя", _partner_name_received([{"role": "other", "content": "ок"}]))
assert_false("ростов не имя", _partner_name_received([{"role": "other", "content": "Ростов"}]))
assert_false("я катя не самопрезентация", _partner_name_received([{"role": "other", "content": "Я катя"}]))

# ===== _extract_name_first_word =====
print("\n=== _extract_name_first_word ===")
assert_eq("лена с запятой", _extract_name_first_word("Лена, приятно познакомиться"), "Лена")
assert_eq("лена с точкой", _extract_name_first_word("Лена. приятно"), "Лена")
assert_eq("просто имя", _extract_name_first_word("Лена"), "Лена")
assert_eq("имя с маленькой", _extract_name_first_word("лена"), None)
assert_eq("пустой", _extract_name_first_word(""), None)
assert_eq("None", _extract_name_first_word(None), None)
assert_eq("приветствие", _extract_name_first_word("Привет, как дела"), None)
assert_eq("служебное", _extract_name_first_word("Круто, согласен"), None)
assert_eq("не имя", _extract_name_first_word("Понятно"), None)
assert_eq("имя в середине", _extract_name_first_word("Очень Лена"), None)
assert_eq("цифры", _extract_name_first_word("19 лет"), None)
assert_eq("первое слово не имя", _extract_name_first_word("Красивая девушка"), None)

# Дополнительные граничные случаи для _already_sent_19
assert_true("роль own 19", _already_sent_19([{"role": "own", "content": "19"}]))
assert_true("роль self 19", _already_sent_19([{"role": "self", "content": "19"}]))

# Дополнительные граничные случаи для check_filters — порядок фильтров
assert_eq("украинский первее грубости",
    check_filters("привiт молчи"), "украинский язык")
assert_eq("украинский первее возраста",
    check_filters("мне 15 и привiт"), "украинский язык")

# ===== ChatState =====
print("\n=== ChatState ===")
state = ChatState()
assert_eq("default partner_name", state.partner_name, None)
assert_eq("default partner_age", state.partner_age, None)
assert_eq("default said_19", state.said_19, False)
assert_eq("default name_sent", state.name_sent, False)
assert_eq("default asked_russian", state.asked_russian, False)
assert_eq("default stage", state.stage, 1)

# ===== _SHORT_AND_YOU =====
print("\n=== _SHORT_AND_YOU ===")
assert_true("'те' в сете", "те" in _SHORT_AND_YOU)
assert_true("'теб' в сете", "теб" in _SHORT_AND_YOU)
assert_true("'и те' в сете", "и те" in _SHORT_AND_YOU)
assert_false("пустая строка", "" in _SHORT_AND_YOU)
assert_false("'привет' не в сете", "привет" in _SHORT_AND_YOU)
assert_false("'тебя' не в сете", "тебя" in _SHORT_AND_YOU)
assert_false("'а те' не в сете", "а те" in _SHORT_AND_YOU)
assert_true("'тебе' в сете", "тебе" in _SHORT_AND_YOU)
assert_false("'ите' не в сете", "ите" in _SHORT_AND_YOU)

# ===== _GREETINGS =====
print("\n=== _GREETINGS ===")
for g in ["привет", "приветик", "здравствуй", "здравствуйте",
           "хай", "хей", "здарова", "салам", "йо"]:
    assert_true(f"приветствие '{g}' в сете", g in _GREETINGS)
assert_false("'приветствие' не в сете", "приветствие" in _GREETINGS)
assert_false("'приветливый' не в сете", "приветливый" in _GREETINGS)
assert_false("'хайп' не в сете", "хайп" in _GREETINGS)
assert_false("'саламандра' не в сете", "саламандра" in _GREETINGS)
assert_false("'здорово' не в сете", "здорово" in _GREETINGS)

# ===== _NOT_NAMES =====
print("\n=== _NOT_NAMES ===")
for nn in ["понятно", "круто", "ладно", "точно", "правда",
           "интересно", "странно", "жаль", "класс", "супер",
           "норм", "прикольно", "конечно", "наверное", "думаю",
           "ага", "ну", "кстати", "вообще", "типа", "короче",
           "пожалуйста", "спасибо", "извини", "прости", "ничего",
           "окей", "ок", "нет", "да", "нормально", "угу"]:
    assert_true(f"'{nn}' в _NOT_NAMES", nn in _NOT_NAMES)
assert_false("'Анна' не в _NOT_NAMES", "анна" in _NOT_NAMES)
assert_false("'Мария' не в _NOT_NAMES", "мария" in _NOT_NAMES)
assert_false("'Катя' не в _NOT_NAMES", "катя" in _NOT_NAMES)
assert_false("'Света' не в _NOT_NAMES", "света" in _NOT_NAMES)

# ===== is_age_question: недостающие паттерны =====
print("\n=== is_age_question (недостающие паттерны) ===")
assert_true("скок", is_age_question("скок"))
assert_true("сколко", is_age_question("сколко тебе"))
assert_true("сколко без контекста", is_age_question("сколко"))
assert_true("сколика", is_age_question("сколика"))
assert_true("скалко", is_age_question("скалко"))
assert_true("теье", is_age_question("теье"))
assert_true("а теье", is_age_question("а теье"))
assert_true("скока тебе", is_age_question("скока тебе"))
assert_true("скок лет", is_age_question("скок лет"))
assert_false("а тебя любят", is_age_question("а тебя любят?"))
assert_false("сколько стоит", is_age_question("сколько стоит?"))

# ===== is_self_introduction: форматы без «я» =====
print("\n=== is_self_introduction (форматы без «я») ===")
assert_true("Лена 19", is_self_introduction("Лена 19"))
assert_true("Аня 17", is_self_introduction("Аня 17"))
assert_true("Катя 18 лет", is_self_introduction("Катя 18 лет"))
assert_true("Маша 19", is_self_introduction("Маша 19"))
assert_true("привет я Катя!", is_self_introduction("Привет я Катя!"))
assert_true("приветик я Маша", is_self_introduction("приветик я Маша"))
assert_true("я Аня.", is_self_introduction("Я Аня."))
assert_true("я Анна-Мария 19", is_self_introduction("Я Анна-Мария 19"))
assert_true("я Аня, приятно", is_self_introduction("Я Аня, приятно"))
assert_true("здарова я Павел", is_self_introduction("Здарова я Павел"))
assert_false("Вика привет", is_self_introduction("Вика привет"))
assert_false("Лена", is_self_introduction("Лена"))
assert_false("Катя, привет", is_self_introduction("Катя, привет"))

# ===== is_ukrainian: дополнительные формы =====
print("\n=== is_ukrainian (дополнительные формы) ===")
assert_true("тобi латиница", is_ukrainian("тобi"))
assert_true("привiт латиница", is_ukrainian("привiт"))
assert_false("украинский язык", is_ukrainian("украинский язык"))
assert_false("по украински", is_ukrainian("по украински"))
assert_false("украинская песня", is_ukrainian("украинская песня"))
assert_true("я украинка с воскл", is_ukrainian("я украинка!"))
assert_true("я украинка и горжусь", is_ukrainian("я украинка и горжусь этим"))
assert_true("я украинец", is_ukrainian("я украинец"))

# ===== _partner_name_received: крайние случаи =====
print("\n=== _partner_name_received (крайние случаи) ===")
assert_true("я Катя с заглавной", _partner_name_received([{"role": "other", "content": "Я Катя"}]))
assert_true("меня зовут анна", _partner_name_received([{"role": "other", "content": "Меня зовут анна"}]))
assert_true("Аня", _partner_name_received([{"role": "other", "content": "Аня"}]))
assert_false("Анна-Мария одно слово с дефисом", _partner_name_received([{"role": "other", "content": "Анна-Мария"}]))
assert_false("я катя с маленькой", _partner_name_received([{"role": "other", "content": "я катя"}]))
assert_false("я маша с маленькой", _partner_name_received([{"role": "other", "content": "я маша"}]))
assert_false("я алина с маленькой", _partner_name_received([{"role": "other", "content": "я алина"}]))

# ===== check_filters: все комбинации приоритетов =====
print("\n=== check_filters (приоритеты) ===")
assert_eq("укр + мус", check_filters("привiт ассалам"), "украинский язык")
assert_eq("укр + груб", check_filters("привiт молчи"), "украинский язык")
assert_eq("укр + возраст", check_filters("привiт мне 15"), "украинский язык")
assert_eq("мус + груб", check_filters("ассалам молчи"), "мусульманская лексика")
assert_eq("мус + возраст", check_filters("ассалам мне 15"), "мусульманская лексика")
assert_eq("груб + возраст", check_filters("молчи мне 15"), "грубость/отказ")
assert_eq("нормальный текст", check_filters("привет как дела"), None)
assert_eq("пустой текст", check_filters(""), None)
# skip_underage
assert_eq("skip_underage=True убирает возраст", check_filters("мне 15", skip_underage=True), None)
assert_eq("skip_underage не убирает укр", check_filters("привiт", skip_underage=True), "украинский язык")

# ===== ChatState._sent дедупликация =====
print("\n=== ChatState._sent дедупликация ===")
state = ChatState()
state._sent = set()
assert_true("_can_send новая строка", _can_send("привет", state._sent))
state._sent.add("привет")
assert_false("_can_send дубликат", _can_send("привет", state._sent))
assert_true("_can_send другая строка", _can_send("как дела", state._sent))
state._sent.add("как дела")
assert_false("_can_send другая тоже дубликат", _can_send("как дела", state._sent))
assert_true("_can_send снова другая", _can_send("норм", state._sent))
assert_true("_can_send пустая строка", _can_send("", state._sent))
state._sent.add("")
assert_false("_can_send пустая строка дубликат", _can_send("", state._sent))

# ===== Stage 3: "тебе" / "лет" больше не ловятся как имена =====
print("\n=== Stage 3: 'тебе'/'лет' не ловятся как имена ===")
# "тебе" не должно быть именем (баг: single-word heuristic)
for bad in ["тебе", "лет"]:
    assert_true(f"'{bad}' в _NOT_NAMES", bad in _NOT_NAMES)
    assert_false(f"'{bad}' не имя по _partner_name_received",
                  _partner_name_received([{"role": "other", "content": bad}]))
# "тебе" — короткая форма "а тебе?" -> and-you
assert_true("'тебе' в _SHORT_AND_YOU", "тебе" in _SHORT_AND_YOU)
# убеждаемся, что полные формы по-прежнему работают
assert_true("тебе? с вопросом в AND_YOU_PATTERNS",
            any(p in "тебе?" for p in AND_YOU_PATTERNS))
assert_false("'а те' не в _SHORT_AND_YOU", "а те" in _SHORT_AND_YOU)

# ===== save_chat_log =====
print("\n=== save_chat_log ===")
cwd = os.getcwd()
with tempfile.TemporaryDirectory() as tmpdir:
    try:
        os.chdir(tmpdir)
        msgs = [
            {"role": "own", "content": "привет"},
            {"role": "other", "content": "привет!"},
            {"role": "own", "content": "19"},
            {"role": "other", "content": "Меня зовут Аня"},
        ]
        result = asyncio.run(save_chat_log(msgs, "19"))
        assert_true("файл создан", os.path.exists(result))
        assert_true("файл в chat_logs/", result.startswith("chat_logs"))
        with open(result, "r", encoding="utf-8") as f:
            content = f.read()
        assert_true("возраст в логе", "19" in content)
        assert_true("теги отправителя", "Я" in content and "Собеседник" in content)
        assert_true("сообщение привет", "привет" in content)
        assert_true("имя Аня", "Аня" in content)
    finally:
        os.chdir(cwd)

# ===== Резюме =====
print(f"\n{'='*40}")
print(f"Результат: {passed} OK, {failed} FAIL")
if failed > 0:
    print("ЕСТЬ ОШИБКИ!")
    sys.exit(1)
else:
    print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
