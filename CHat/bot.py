"""Amor-Bot v1.0 - Main orchestrator"""

import asyncio
import random
import time
import sys
import threading
from typing import Optional

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from config import (
    REMOTE_DEBUGGING_PORT,
    USER_DATA_DIR,
    SCAN_INTERVAL,
    SILENCE_TIMEOUT,
    SELECTORS,
    OPENERS,
    TELEGRAM_USERNAME,
)
from observer import Observer
from brain import Brain
from executor import Executor


class CommandQueue:
    """Поток-безопасная очередь для команд"""
    def __init__(self):
        self.commands = []
        self.lock = threading.Lock()
    
    def put(self, cmd: str):
        with self.lock:
            self.commands.append(cmd)
    
    def get(self) -> Optional[str]:
        with self.lock:
            if self.commands:
                return self.commands.pop(0)
            return None


# Глобальная очередь команд
command_queue = CommandQueue()

def console_reader():
    """Функция для чтения ввода в отдельном потоке"""
    while True:
        try:
            cmd = input()
            if cmd:
                command_queue.put(cmd.strip())
        except Exception as e:
            print(f"Ошибка ввода: {e}")


class State:
    """Bot state machine states"""
    IDLE = "idle"
    SENT_HELLO = "sent_hello"  # Отправил "Привет"
    SENT_AGE = "sent_age"  # Отправил "сколько лет"
    DONE = "done"  # Закончил работу
    PAUSED = "paused"  # Ручное управление


class AmorBot:
    """Main bot orchestrator for Nekto.me automation"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.observer: Optional[Observer] = None
        self.brain: Optional[Brain] = None
        self.executor: Optional[Executor] = None
        self.state = State.IDLE
        self.last_message_time: float = 0
        self.conversation_active: bool = False
        self.manual_control: bool = False  # Flag for manual control
        self.opener_sent: bool = False  # Флаг: первое сообщение отправлено
        self.last_processed_message: str = ""  # Последнее обработанное сообщение
        self.console_reader: Optional[ConsoleReader] = None
        self.debug_mode: bool = False  # Debug output toggle
        self.chat_ended_reported: bool = False  # Prevent spam
        self.received_response: bool = False  # Got at least one response

    async def connect_to_browser(self) -> None:
        """Connect to existing Chrome instance via remote debugging"""
        import warnings
        
        # Suppress asyncio transport warnings
        warnings.filterwarnings("ignore", category=ResourceWarning)
        
        playwright = await async_playwright().start()

        # Connect to existing Chrome with user data directory
        # Use 127.0.0.1 instead of localhost to avoid IPv6 issues
        ws_endpoint = f"http://127.0.0.1:{REMOTE_DEBUGGING_PORT}"

        try:
            self.browser = await playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{REMOTE_DEBUGGING_PORT}",
                timeout=30000
            )
            if self.debug_mode:
                print(f"✓ Connected to Chrome on port {REMOTE_DEBUGGING_PORT}")

            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        except Exception as e:
            if self.debug_mode:
                print(f"✗ Failed to connect to Chrome: {e}")
                print(f"Trying to launch Chrome directly...")

            # Fallback: Launch Chrome directly with Playwright
            self.context = await playwright.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR if USER_DATA_DIR else None,
                args=[
                    f"--remote-debugging-port={REMOTE_DEBUGGING_PORT}",
                    "--no-first-run",
                ],
                headless=False,
                timeout=30000
            )
            if self.debug_mode:
                print(f"✓ Launched Chrome on port {REMOTE_DEBUGGING_PORT}")
            self.browser = None  # Persistent context doesn't have browser object
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Navigate to Nekto.me chat with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Go directly to chat page
                await self.page.goto("https://nekto.me/chat/", wait_until="networkidle", timeout=30000)
                if self.debug_mode:
                    print("✓ Navigated to nekto.me/chat/")

                # Save page HTML for debugging selectors
                html = await self.page.content()
                with open("page_debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"✗ Failed to navigate to nekto.me after {max_retries} attempts: {e}")
                    raise
                await asyncio.sleep(2)

    async def initialize(self) -> None:
        """Initialize all bot modules"""
        await self.connect_to_browser()

        self.observer = Observer(self.page)
        self.brain = Brain()
        self.executor = Executor(self.page)

        if self.debug_mode:
            print("✓ All modules initialized")

    async def start_new_chat(self) -> None:
        """Start a new chat session"""
        # Защита: не запускаем новый чат если уже в процессе
        if self.state in [State.SENT_HELLO, State.SENT_AGE, State.DONE]:
            return

        # Сбрасываем флаги для нового чата
        self.last_processed_message = ""

        # First check if chat is already active (input field exists)
        # Debug: Try each selector individually
        input_selectors = SELECTORS["input_field"].split(", ")
        for selector in input_selectors:
            try:
                elem = await self.page.query_selector(selector)
                if elem:
                    is_visible = await elem.is_visible()
                    if is_visible:
                        class_attr = await elem.get_attribute("class") or ""
                        id_attr = await elem.get_attribute("id") or ""

                        if "recaptcha" not in id_attr.lower() and "swal" not in class_attr.lower():
                            # Проверяем, есть ли уже сообщения в чате
                            incoming_msgs = await self.page.query_selector_all(SELECTORS["incoming_msg"])
                            outgoing_msgs = await self.page.query_selector_all(SELECTORS["outgoing_msg"])
                            total_msgs = len(incoming_msgs) + len(outgoing_msgs)
                            
                            self.conversation_active = True
                            self.state = State.SENT_HELLO
                            self.last_message_time = time.time()
                            
                            # Если уже есть сообщения - не спамим "Привет"
                            if total_msgs > 0:
                                self.opener_sent = True
                            else:
                                self.opener_sent = False
                                await self.send_opener()
                            return
            except Exception:
                continue

        # First, try to click "Start chat" button if on settings page
        try:
            selectors_to_try = [
                "#searchCompanyBtn",
                "button:has-text('Начать чат')",
                "button:has-text('Начать')",
                ".search-btn",
                ".btn-primary"
            ]

            for selector in selectors_to_try:
                try:
                    new_chat_btn = await self.page.query_selector(selector)
                    if new_chat_btn:
                        is_visible = await new_chat_btn.is_visible()
                        if is_visible:
                            await asyncio.sleep(1)
                            await new_chat_btn.click()
                            self.opener_sent = False
                            await asyncio.sleep(2)
                            break
                except Exception:
                    continue

        except Exception:
            pass

        # Wait for chat to connect and input field to appear
        # Wait up to 90 seconds for chat to be ready
        for i in range(90):
            await asyncio.sleep(1)

            # Check if chat is ready (input field visible)
            try:
                input_selectors = SELECTORS["input_field"].split(", ")
                for selector in input_selectors:
                    input_field = await self.page.query_selector(selector)
                    if input_field:
                        is_visible = await input_field.is_visible()

                        # Make sure it's not a captcha textarea
                        class_attr = await input_field.get_attribute("class") or ""
                        id_attr = await input_field.get_attribute("id") or ""

                        if "recaptcha" in id_attr.lower() or "swal" in class_attr.lower():
                            continue

                        if is_visible:
                            self.conversation_active = True
                            self.state = State.SENT_HELLO
                            self.last_message_time = time.time()
                            if not self.opener_sent:
                                await self.send_opener()
                            return
            except Exception:
                pass

        self.state = State.IDLE

    async def send_opener(self) -> None:
        """Send the first message (Привет)"""
        if self.opener_sent:
            return  # Уже отправили, не спамим

        if self.debug_mode:
            print("→ Sending opener: Привет")
        await self.executor.send_message("Привет")
        self.opener_sent = True
        self.state = State.SENT_HELLO

    async def handle_conversation(self) -> None:
        """Main conversation loop"""
        while True:
            # Если бот закончил - выходим с задержкой
            if self.state == State.DONE:
                if self.debug_mode:
                    print("✓ Бот завершил работу")
                await asyncio.sleep(1.0)  # Даем время на завершение операций
                await self.cleanup()
                break

            # Если ручное управление - пропускаем обработку ботом
            if self.manual_control or self.state == State.PAUSED:
                await asyncio.sleep(SCAN_INTERVAL / 1000)
                continue

            if not self.conversation_active:
                await self.wait_for_new_chat()
                continue

            # Check for chat end - only after we've sent opener AND received a response
            if self.opener_sent and self.received_response and self.state != State.DONE:
                chat_ended = await self.observer.is_chat_ended()
                if chat_ended and not self.chat_ended_reported:
                    self.chat_ended_reported = True
                    if self.debug_mode:
                        print("→ Chat ended by interlocutor")
                    self.state = State.DONE
                    self.conversation_active = False
                    continue

            # Get new messages
            new_messages = await self.observer.get_new_messages()

            if new_messages:
                for msg in new_messages:
                    if msg["role"] == "other":
                        self.last_message_time = time.time()
                        self.received_response = True
                        await self.process_incoming_message(msg["content"])

            await asyncio.sleep(SCAN_INTERVAL / 1000)

    async def process_incoming_message(self, message: str) -> None:
        """Process incoming message and generate response"""
        # Защита от повторной обработки одного сообщения
        if message == self.last_processed_message:
            return
        self.last_processed_message = message

        if self.debug_mode:
            print(f"← Received: {message}")

        # Если отправили "Привет" и получили ответ - отправляем "Сколько лет" и выключаемся
        if self.state == State.SENT_HELLO:
            if self.debug_mode:
                print("→ Sending: Сколько лет")
            await self.executor.send_message("Сколько лет")
            self.state = State.SENT_AGE
            return

        # Если уже отправили "Сколько лет" - выключаемся
        if self.state == State.SENT_AGE:
            if self.debug_mode:
                print("✓ Бот завершил работу (отправил 2 сообщения)")
            self.state = State.DONE
            return

    async def handle_reset(self) -> None:
        """Handle chat reset and return to IDLE"""
        self.brain.clear_context()
        self.state = State.IDLE
        self.manual_control = False
        self.opener_sent = False  # Сбрасываем для нового чата
        self.last_processed_message = ""  # Сбрасываем последнее сообщение
        self.chat_ended_reported = False  # Сбрасываем флаг для нового чата
        self.received_response = False  # Сбрасываем флаг ответа

    async def handle_console_input(self) -> None:
        """Handle console commands for manual control"""
        # Запускаем поток для чтения консоли
        console_thread = threading.Thread(target=console_reader, daemon=True)
        console_thread.start()

        print("=== КОМАНДЫ УПРАВЛЕНИЯ ===")
        print("/stop   - Пауза, взять управление")
        print("/start  - Продолжить, отдать управление боту")
        print("/send <текст> - Отправить сообщение вручную")
        print("/exit   - Выйти из чата и завершить")
        print("/help   - Эта справка")
        print("/skip   - Пропустить текущий чат")
        print("/debug  - Вкл/выкл отладочные сообщения")
        print("===========================\n")

        while True:
            await asyncio.sleep(0.2)  # Даём время на ввод

            # Проверяем команду из очереди
            command = command_queue.get()
            if not command:
                continue

            command = command.lower()

            if command in ["/stop", "/pause"]:
                if not self.manual_control:
                    self.manual_control = True
                    self.state = State.PAUSED
                    if self.debug_mode:
                        print("\n🔴 БОТ НА ПАУЗЕ - управление у тебя")
                        print("   Команды: /send <текст>, /start, /exit, /help\n")
                else:
                    print("Бот уже на паузе")

            elif command == "/start":
                if self.manual_control:
                    self.manual_control = False
                    # Восстанавливаем предыдущее состояние
                    if self.state == State.PAUSED:
                        self.state = State.ENGAGE
                    if self.debug_mode:
                        print("\n🟢 БОТ АКТИВЕН - управление у бота\n")
                else:
                    print("Бот уже активен")

            elif command == "/exit":
                if self.debug_mode:
                    print("\n👋 Завершение работы...")
                if self.executor and self.conversation_active:
                    await self.executor.send_message("пока")
                await self.cleanup()
                break

            elif command == "/help":
                print("\n=== КОМАНДЫ УПРАВЛЕНИЯ ===")
                print("/stop   - Пауза, взять управление")
                print("/start  - Продолжить, отдать управление боту")
                print("/send <текст> - Отправить сообщение вручную")
                print("/exit   - Выйти из чата и завершить")
                print("/help   - Эта справка")
                print("/skip   - Пропустить текущий чат")
                print("/debug  - Вкл/выкл отладочные сообщения\n")

            elif command.startswith("/send "):
                if self.manual_control:
                    text = command[6:].strip()
                    if text and self.conversation_active:
                        if self.debug_mode:
                            print(f"→ Отправка: {text}")
                        await self.executor.send_message(text)
                else:
                    print("Сначала нажми /stop для ручного управления")

            elif command == "/skip":
                if self.debug_mode:
                    print("→ Пропуск текущего чата...")
                self.conversation_active = False
                self.state = State.IDLE
                await self.handle_reset()

            elif command == "/debug":
                self.debug_mode = not self.debug_mode
                status = "включен" if self.debug_mode else "выключен"
                print(f"✓ Отладочный режим {status}")

            elif command.startswith("/"):
                print(f"Неизвестная команда: {command}")
                print("Введи /help для списка команд\n")

    async def wait_for_new_chat(self) -> None:
        """Wait in IDLE state for new chat opportunity"""
        if self.state == State.IDLE:
            await self.start_new_chat()
        elif self.state == State.DONE:
            # Бот завершил работу, не запускаем новый чат
            pass

    async def run(self) -> None:
        """Main bot run loop"""
        try:
            await self.initialize()

            # Запускаем обработчик консоли в фоновом режиме
            console_task = asyncio.create_task(self.handle_console_input())

            print("Amor-Bot запущен. Введи /help для команд")

            # Start conversation loop
            await self.start_new_chat()
            await self.handle_conversation()

        except KeyboardInterrupt:
            if self.debug_mode:
                print("\n→ Бот остановлен пользователем")
        except Exception as e:
            print(f"✗ Ошибка бота: {e}")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self) -> None:
        """Cleanup resources"""
        try:
            if self.context:
                await self.context.close()
                if self.debug_mode:
                    print("✓ Context closed")
        except Exception as e:
            if self.debug_mode:
                print(f"Context cleanup error: {e}")
        
        try:
            if self.browser:
                await self.browser.close()
                if self.debug_mode:
                    print("✓ Browser closed")
        except Exception as e:
            if self.debug_mode:
                print(f"Browser cleanup error: {e}")
        
        # Give asyncio time to clean up transports
        await asyncio.sleep(0.1)


async def main():
    """Entry point"""
    bot = AmorBot()
    await bot.run()


if __name__ == "__main__":
    import warnings
    import asyncio
    
    # Suppress asyncio transport errors on Windows Python 3.14+
    # Monkey-patch the _warn function to suppress these errors
    def silent_warn(*args, **kwargs):
        pass
    
    try:
        import asyncio.proactor_events
        asyncio.proactor_events._warn = silent_warn
    except Exception:
        pass
    
    warnings.filterwarnings("ignore", category=ResourceWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
