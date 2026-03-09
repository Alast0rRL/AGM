"""Amor-Bot v1.0 - Main orchestrator"""

import asyncio
import random
import time
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


class State:
    """Bot state machine states"""
    IDLE = "idle"
    HOOK = "hook"
    ENGAGE = "engage"
    CONVERSION = "conversion"
    RESET = "reset"


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

    async def connect_to_browser(self) -> None:
        """Connect to existing Chrome instance via remote debugging"""
        playwright = await async_playwright().start()

        # Connect to existing Chrome with user data directory
        # Use 127.0.0.1 instead of localhost to avoid IPv6 issues
        ws_endpoint = f"http://127.0.0.1:{REMOTE_DEBUGGING_PORT}"

        try:
            self.browser = await playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{REMOTE_DEBUGGING_PORT}",
                timeout=30000
            )
            print(f"✓ Connected to Chrome on port {REMOTE_DEBUGGING_PORT}")
            
            self.context = self.browser.contexts[0]
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        except Exception as e:
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
            print(f"✓ Launched Chrome on port {REMOTE_DEBUGGING_PORT}")
            self.browser = None  # Persistent context doesn't have browser object
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

        # Navigate to Nekto.me chat with retry logic
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Go directly to chat page
                await self.page.goto("https://nekto.me/chat/", wait_until="networkidle", timeout=30000)
                print("✓ Navigated to nekto.me/chat/")
                
                # Save page HTML for debugging selectors
                html = await self.page.content()
                with open("page_debug.html", "w", encoding="utf-8") as f:
                    f.write(html)
                print("📄 Saved page HTML to page_debug.html for selector debugging")
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"✗ Failed to navigate to nekto.me after {max_retries} attempts: {e}")
                    raise
                print(f"⚠ Navigation attempt {attempt + 1} failed, retrying...")
                await asyncio.sleep(2)

    async def initialize(self) -> None:
        """Initialize all bot modules"""
        await self.connect_to_browser()
        
        self.observer = Observer(self.page)
        self.brain = Brain()
        self.executor = Executor(self.page)
        
        print("✓ All modules initialized")

    async def start_new_chat(self) -> None:
        """Start a new chat session"""
        print("→ Starting new chat...")

        # First check if chat is already active (input field exists)
        print("→ Checking for active chat...")
        
        # Debug: Try each selector individually
        input_selectors = SELECTORS["input_field"].split(", ")
        for selector in input_selectors:
            try:
                elem = await self.page.query_selector(selector)
                if elem:
                    is_visible = await elem.is_visible()
                    print(f"  ✓ Found input with selector '{selector}', visible: {is_visible}")
                    if is_visible:
                        class_attr = await elem.get_attribute("class") or ""
                        id_attr = await elem.get_attribute("id") or ""
                        
                        if "recaptcha" not in id_attr.lower() and "swal" not in class_attr.lower():
                            print("✓ Chat already active, input field found")
                            self.conversation_active = True
                            self.state = State.HOOK
                            self.last_message_time = time.time()
                            await self.send_opener()
                            return
            except Exception as e:
                print(f"  Selector '{selector}' failed: {e}")
                continue

        # First, try to click "Start chat" button if on settings page
        try:
            print("→ Looking for 'Start chat' button...")

            # Try multiple selectors
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
                        print(f"  Found button with selector '{selector}', visible: {is_visible}")
                        if is_visible:
                            await asyncio.sleep(1)
                            await new_chat_btn.click()
                            print("✓ 'Start chat' button clicked")
                            await asyncio.sleep(2)
                            break
                except Exception as e:
                    print(f"  Selector '{selector}' failed: {e}")
                    continue

        except Exception as e:
            print(f"⚠ Could not click start button: {e}")

        # Wait for chat to connect and input field to appear
        print("⏳ Waiting for chat to connect (solve captcha if shown)...")

        # Wait up to 90 seconds for chat to be ready
        for i in range(90):
            await asyncio.sleep(1)

            # Check if chat is ready (input field visible)
            try:
                # Debug: Try each selector individually
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
                            print(f"✓ Input field found with selector '{selector}', chat is ready")
                            self.conversation_active = True
                            self.state = State.HOOK
                            self.last_message_time = time.time()
                            await self.send_opener()
                            return
            except Exception as e:
                pass

            if (i + 1) % 10 == 0:
                print(f"⏳ Still waiting for chat... ({i + 1}s)")
                # Debug: Save current page state
                try:
                    url = self.page.url
                    print(f"  Current URL: {url}")
                except:
                    pass

        print("✗ Timeout waiting for chat to connect")
        self.state = State.IDLE

    async def send_opener(self) -> None:
        """Send the first message (opener)"""
        opener = random.choice(OPENERS)
        print(f"→ Sending opener: {opener}")
        
        await self.executor.send_message(opener)
        self.state = State.ENGAGE

    async def handle_conversation(self) -> None:
        """Main conversation loop"""
        while True:
            if not self.conversation_active:
                await self.wait_for_new_chat()
                continue

            # Check for chat end
            chat_ended = await self.observer.is_chat_ended()
            if chat_ended:
                print("→ Chat ended by interlocutor")
                self.state = State.RESET
                self.conversation_active = False
                await self.handle_reset()
                continue

            # Check for silence timeout
            if time.time() - self.last_message_time > SILENCE_TIMEOUT / 1000:
                print("→ Silence timeout, leaving chat")
                await self.executor.send_message("скучно с тобой, пока")
                self.state = State.RESET
                self.conversation_active = False
                continue

            # Get new messages
            new_messages = await self.observer.get_new_messages()
            
            if new_messages:
                for msg in new_messages:
                    if msg["role"] == "other":
                        self.last_message_time = time.time()
                        await self.process_incoming_message(msg["content"])

            await asyncio.sleep(SCAN_INTERVAL / 1000)

    async def process_incoming_message(self, message: str) -> None:
        """Process incoming message and generate response"""
        print(f"← Received: {message}")

        # Check for quick responses (M/J etc.)
        quick_response = self.brain.get_quick_response(message)
        if quick_response:
            print(f"→ Quick response: {quick_response}")
            await self.executor.send_message(quick_response)
            return

        # Check for aggression
        if self.brain.detect_aggression(message):
            print("→ Aggression detected, leaving chat")
            await self.executor.send_message("пока")
            self.state = State.RESET
            self.conversation_active = False
            return

        # Generate response via LLM
        response = await self.brain.generate_response(message)
        
        if response:
            print(f"→ Sending: {response}")
            await self.executor.send_message(response)

            # Check if conversion message was sent
            if self.brain.is_conversion_message(response):
                print("→ Conversion message sent, waiting for response")
                # Could add special handling here

    async def handle_reset(self) -> None:
        """Handle chat reset and return to IDLE"""
        self.brain.clear_context()
        self.state = State.IDLE
        await asyncio.sleep(random.uniform(1, 3))
        await self.start_new_chat()

    async def wait_for_new_chat(self) -> None:
        """Wait in IDLE state for new chat opportunity"""
        if self.state == State.IDLE:
            await self.start_new_chat()

    async def run(self) -> None:
        """Main bot run loop"""
        try:
            await self.initialize()
            
            # Start conversation loop
            await self.start_new_chat()
            await self.handle_conversation()
            
        except KeyboardInterrupt:
            print("\n→ Bot stopped by user")
        except Exception as e:
            print(f"✗ Bot error: {e}")
            raise
        finally:
            await self.cleanup()

    async def cleanup(self) -> None:
        """Cleanup resources"""
        if self.context:
            await self.context.close()
            print("✓ Context closed")
        if self.browser:
            await self.browser.close()
            print("✓ Browser closed")


async def main():
    """Entry point"""
    bot = AmorBot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
