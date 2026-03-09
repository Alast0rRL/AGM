"""Amor-Bot v1.0 - Simple Nekto.me automation"""

import asyncio
import time
import threading
import sys
import logging
from typing import Optional
from datetime import datetime

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from config import (
    REMOTE_DEBUGGING_PORT,
    USER_DATA_DIR,
    SCAN_INTERVAL,
    SELECTORS,
    TELEGRAM_USERNAME,
)
from observer import Observer
from executor import Executor


# Setup logging
log_filename = f"bot_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_filename, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class CommandQueue:
    """Thread-safe command queue"""
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


command_queue = CommandQueue()


def console_reader():
    """Read console input in separate thread"""
    while True:
        try:
            cmd = input()
            if cmd:
                command_queue.put(cmd.strip())
        except Exception:
            pass


class AmorBot:
    """Simple bot for Nekto.me chat automation"""

    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.observer: Optional[Observer] = None
        self.executor: Optional[Executor] = None
        
        self.state = "idle"  # idle, sent_hello, sent_age, manual
        self.conversation_active = False
        self.manual_control = False
        self.opener_sent = False
        self.age_sent = False  # Флаг: "Сколько лет" отправлено
        self.last_processed_message = ""
        self.chat_ended_reported = False
        self.received_response = False

    async def connect_to_browser(self) -> None:
        """Connect to Chrome via remote debugging"""
        playwright = await async_playwright().start()

        try:
            # Try to connect to existing Chrome
            self.browser = await playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{REMOTE_DEBUGGING_PORT}",
                timeout=30000
            )
            logger.info(f"✓ Connected to Chrome on port {REMOTE_DEBUGGING_PORT}")

            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        except Exception as e:
            logger.warning(f"✗ Failed to connect: {e}")
            logger.warning("Trying to launch Chrome...")

            # Fallback: launch Chrome directly
            self.context = await playwright.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR if USER_DATA_DIR else None,
                args=[
                    f"--remote-debugging-port={REMOTE_DEBUGGING_PORT}",
                    "--no-first-run",
                ],
                headless=False,
                timeout=30000
            )
            logger.info(f"✓ Launched Chrome on port {REMOTE_DEBUGGING_PORT}")
            self.browser = None
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Navigate to Nekto.me chat
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self.page.goto("https://nekto.me/chat/", wait_until="networkidle", timeout=30000)
                logger.info("✓ Navigated to nekto.me/chat/")

                # Save page HTML for debugging
                html = await self.page.content()
                with open("page_debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"✗ Failed to navigate: {e}")
                    raise
                await asyncio.sleep(2)

    async def initialize(self) -> None:
        """Initialize bot modules"""
        await self.connect_to_browser()
        self.observer = Observer(self.page)
        self.executor = Executor(self.page)
        logger.info("✓ Bot initialized")

    async def start_new_chat(self) -> None:
        """Start a new chat session"""
        if self.state in ["sent_hello", "sent_age", "manual"]:
            return

        # Reset flags
        self.last_processed_message = ""
        self.received_response = False
        self.chat_ended_reported = False
        self.opener_sent = False
        self.age_sent = False
        if self.observer:
            self.observer.clear_history()

        # Check if chat is already active
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
                            # Check existing messages
                            incoming_msgs = await self.page.query_selector_all(SELECTORS["incoming_msg"])
                            outgoing_msgs = await self.page.query_selector_all(SELECTORS["outgoing_msg"])
                            total_msgs = len(incoming_msgs) + len(outgoing_msgs)

                            self.conversation_active = True
                            self.state = "sent_hello"
                            self.last_message_time = time.time()

                            if total_msgs > 0:
                                self.opener_sent = True
                                # Check if age question was already asked
                                for msg in outgoing_msgs:
                                    text = await msg.text_content()
                                    if text and any(p in text.lower() for p in ["скок лет", "сколько лет", "возраст", "лет"]):
                                        self.age_sent = True
                                        self.state = "sent_age"
                                        break
                            else:
                                self.opener_sent = False
                                await self.send_opener()
                            return
            except Exception:
                continue

        # Try to click "Start chat" button
        try:
            selectors_to_try = [
                "#searchCompanyBtn",
                "button:has-text('Начать чат')",
                "button:has-text('Начать')",
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

        # Wait for chat to connect (up to 90 seconds)
        for i in range(90):
            await asyncio.sleep(1)

            try:
                input_selectors = SELECTORS["input_field"].split(", ")
                for selector in input_selectors:
                    input_field = await self.page.query_selector(selector)
                    if input_field:
                        is_visible = await input_field.is_visible()
                        class_attr = await input_field.get_attribute("class") or ""
                        id_attr = await input_field.get_attribute("id") or ""

                        if "recaptcha" in id_attr.lower() or "swal" in class_attr.lower():
                            continue

                        if is_visible:
                            self.conversation_active = True
                            self.state = "sent_hello"
                            self.last_message_time = time.time()
                            if not self.opener_sent:
                                await self.send_opener()
                            return
            except Exception:
                pass

        self.state = "idle"

    async def send_opener(self) -> None:
        """Send first message (Привет)"""
        if self.opener_sent:
            return

        logger.info("→ Sending: Привет")
        await self.executor.send_message("Привет")
        self.opener_sent = True
        self.state = "sent_hello"

    async def handle_conversation(self) -> None:
        """Main conversation loop"""
        while True:
            # If manual control - just wait
            if self.manual_control:
                await asyncio.sleep(SCAN_INTERVAL / 1000)
                continue

            if not self.conversation_active:
                await self.wait_for_new_chat()
                continue

            # Check for age question in outgoing messages (in case user sent it manually)
            if self.state == "sent_hello" and not self.age_sent:
                outgoing_msgs = await self.page.query_selector_all(SELECTORS["outgoing_msg"])
                for msg in outgoing_msgs:
                    text = await msg.text_content()
                    if text and any(p in text.lower() for p in ["скок лет", "сколько лет", "возраст", "лет"]):
                        self.age_sent = True
                        self.state = "sent_age"
                        logger.info("→ Detected age question sent manually")
                        break

            # Check if chat ended
            if self.opener_sent and self.received_response:
                chat_ended = await self.observer.is_chat_ended()
                if chat_ended and not self.chat_ended_reported:
                    self.chat_ended_reported = True
                    logger.info("→ Chat ended by interlocutor")
                    # Reset and start new chat
                    self.conversation_active = False
                    self.state = "idle"
                    self.opener_sent = False
                    self.age_sent = False
                    self.received_response = False
                    if self.observer:
                        self.observer.clear_history()
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
        """Process incoming message"""
        if message == self.last_processed_message:
            return
        self.last_processed_message = message

        logger.info(f"← Received: {message}")

        # Sent "Привет", got response → send "Сколько лет" (only once!)
        if self.state == "sent_hello":
            if not self.age_sent:
                self.age_sent = True  # Set flag BEFORE sending to prevent race
                logger.info("→ Sending: Сколько лет")
                await self.executor.send_message("Сколько лет")
                self.state = "sent_age"
            return

        # Sent "Сколько лет", got response → give manual control
        if self.state == "sent_age":
            logger.info("→ Manual control enabled")
            self.manual_control = True
            print("\n" + "=" * 50)
            print("🔴 БОТ НА ПАУЗЕ - управление у вас")
            print("   /send <текст> - отправить сообщение")
            print("   /start - вернуть управление боту")
            print("   /exit - выйти")
            print("   /skip - пропустить чат")
            print("=" * 50 + "\n")
            return

    async def handle_console_input(self) -> None:
        """Handle console commands"""
        console_thread = threading.Thread(target=console_reader, daemon=True)
        console_thread.start()

        logger.info("=== КОМАНДЫ ===")
        logger.info("/stop - Пауза, /start - Продолжить, /send <текст> - Отправить")
        logger.info("/exit - Выйти, /skip - Пропустить чат")

        while True:
            await asyncio.sleep(0.2)

            command = command_queue.get()
            if not command:
                continue

            command_lower = command.lower()

            if command_lower in ["/stop", "/pause"]:
                if not self.manual_control:
                    self.manual_control = True
                    logger.info("🔴 БОТ НА ПАУЗЕ")

            elif command_lower == "/start":
                if self.manual_control:
                    self.manual_control = False
                    if self.state == "sent_age":
                        self.state = "manual"
                    logger.info("🟢 БОТ АКТИВЕН")

            elif command_lower == "/exit":
                logger.info("👋 Завершение...")
                if self.executor and self.conversation_active:
                    await self.executor.send_message("пока")
                await self.cleanup()
                break

            elif command_lower.startswith("/send "):
                if self.manual_control:
                    text = command[6:].strip()
                    if text and self.conversation_active:
                        logger.info(f"→ Отправка: {text}")
                        await self.executor.send_message(text)
                else:
                    logger.warning("Сначала /stop для ручного управления")

            elif command_lower == "/skip":
                logger.info("→ Пропуск чата...")
                self.conversation_active = False
                self.state = "idle"
                self.opener_sent = False
                self.age_sent = False
                self.received_response = False
                self.manual_control = False
                if self.observer:
                    self.observer.clear_history()

            elif command_lower.startswith("/"):
                logger.warning(f"Неизвестная команда: {command}")

    async def wait_for_new_chat(self) -> None:
        """Wait for new chat"""
        if self.state == "idle":
            await asyncio.sleep(2)
            await self.start_new_chat()

    async def run(self) -> None:
        """Main bot loop"""
        try:
            await self.initialize()

            # Start console handler
            console_task = asyncio.create_task(self.handle_console_input())

            logger.info("Amor-Bot запущен")

            # Start conversation
            await self.start_new_chat()
            await self.handle_conversation()

        except KeyboardInterrupt:
            logger.info("→ Бот остановлен")
        except Exception as e:
            logger.error(f"✗ Ошибка: {e}", exc_info=True)
        finally:
            await self.cleanup()

    async def cleanup(self) -> None:
        """Cleanup resources"""
        try:
            if self.context:
                await self.context.close()
                logger.info("✓ Context closed")
        except Exception as e:
            logger.error(f"Context cleanup error: {e}")

        try:
            if self.browser:
                await self.browser.close()
                logger.info("✓ Browser closed")
        except Exception as e:
            logger.error(f"Browser cleanup error: {e}")

        await asyncio.sleep(0.1)


async def main():
    """Entry point"""
    bot = AmorBot()
    await bot.run()


if __name__ == "__main__":
    import warnings
    import os
    import logging

    # Suppress asyncio errors on Windows
    os.environ["PYTHONASYNCIODEBUG"] = "0"
    logging.getLogger("asyncio").setLevel(logging.CRITICAL)

    # Filter stderr
    original_stderr = sys.stderr
    error_buffer = ""

    class StderrFilter:
        def write(self, text):
            global error_buffer
            error_buffer += text

            if "\n" in error_buffer:
                lines = error_buffer.split("\n")
                error_buffer = lines[-1]

                block_text = "\n".join(lines[:-1])
                is_error = any(p in block_text for p in [
                    "_ProactorBasePipeTransport",
                    "unclosed transport",
                    "I/O operation on closed pipe",
                    "BaseSubprocessTransport",
                    "proactor_events.py",
                    "windows_utils.py",
                ])

                if not is_error:
                    for line in lines[:-1]:
                        if line.strip():
                            original_stderr.write(line + "\n")

        def flush(self):
            original_stderr.flush()

        def isatty(self):
            return original_stderr.isatty()

    sys.stderr = StderrFilter()

    warnings.filterwarnings("ignore", category=ResourceWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
