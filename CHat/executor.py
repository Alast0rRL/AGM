"""Executor Module - Input simulation and message sending"""

import asyncio
import random
from playwright.async_api import Page

from config import (
    SELECTORS,
    TYPING_DELAY_MIN,
    TYPING_DELAY_MAX,
    THINKING_DELAY_BASE,
    DELAY_VARIANCE,
)


class Executor:
    """
    Handles message input and sending with human-like behavior.
    Implements typing delays and "thinking" pauses.
    """

    def __init__(self, page: Page):
        self.page = page
        self.typing_delay_min = TYPING_DELAY_MIN
        self.typing_delay_max = TYPING_DELAY_MAX
        self.thinking_delay_base = THINKING_DELAY_BASE
        self.delay_variance = DELAY_VARIANCE

    def _randomize_delay(self, delay: float) -> float:
        """Add variance to delay for anti-detection"""
        variance = delay * self.delay_variance
        return delay + random.uniform(-variance, variance)

    def _calculate_thinking_delay(self, message_length: int) -> float:
        """
        Calculate thinking delay based on incoming message length.
        Longer messages = more thinking time.
        """
        base = self.thinking_delay_base
        per_char = 50  # ms per character
        calculated = base + (message_length * per_char)
        return self._randomize_delay(calculated)

    def _get_typing_delay(self) -> float:
        """Get randomized typing delay between keystrokes"""
        return random.uniform(self.typing_delay_min, self.typing_delay_max)

    async def _get_input_field(self):
        """Get input field element - try multiple selectors"""
        # Try each selector individually
        input_selectors = SELECTORS["input_field"].split(", ")
        
        for selector in input_selectors:
            try:
                input_field = await self.page.wait_for_selector(
                    selector.strip(),
                    state="visible",
                    timeout=2000
                )
                if input_field:
                    print(f"  [Executor] Found input with selector: {selector.strip()}")
                    return input_field
            except Exception:
                continue
        
        # If no selector worked, raise error
        raise Exception(f"Could not find input field with any selector: {input_selectors}")

    async def _focus_input(self) -> None:
        """Focus the input field"""
        input_field = await self._get_input_field()
        await input_field.click()
        await asyncio.sleep(0.1)  # Small pause after focus

    async def _type_text(self, text: str) -> None:
        """Type text with human-like delays"""
        input_field = await self._get_input_field()

        typing_delay = self._get_typing_delay()

        # Check if it's a contenteditable div
        tag_name = await input_field.evaluate("el => el.tagName")
        
        if tag_name.lower() == "div":
            # For contenteditable div, use fill instead of press
            await input_field.fill(text)
            await asyncio.sleep(typing_delay / 1000)
        else:
            # Type character by character with delays for textarea
            for char in text:
                await input_field.press(char)
                await asyncio.sleep(typing_delay / 1000)  # Convert to seconds

        # Random pause before sending
        await asyncio.sleep(random.uniform(0.2, 0.5))

    async def _send_message(self) -> None:
        """Press Enter to send message"""
        input_field = await self._get_input_field()
        
        # Try pressing Enter first
        try:
            await input_field.press("Enter")
            print("  → Sent via Enter key")
        except Exception as e:
            print(f"  ⚠ Enter key failed: {e}")
            # If Enter doesn't work, try clicking the send button
            try:
                send_btn = await self.page.query_selector(SELECTORS["send_button"])
                if send_btn:
                    is_visible = await send_btn.is_visible()
                    print(f"  → Found send button, visible: {is_visible}")
                    if is_visible:
                        await send_btn.click()
                        print("  → Sent via button click")
            except Exception as e2:
                print(f"  ⚠ Send button failed: {e2}")

    async def send_message(self, text: str, incoming_message_length: int = 0) -> None:
        """
        Send a complete message with human-like behavior.
        
        Args:
            text: Message text to send
            incoming_message_length: Length of incoming message (for thinking delay)
        """
        try:
            # Focus input
            await self._focus_input()
            
            # Thinking delay (if responding to something)
            if incoming_message_length > 0:
                thinking_delay = self._calculate_thinking_delay(incoming_message_length)
                await asyncio.sleep(thinking_delay / 1000)
            
            # Type the message
            await self._type_text(text)
            
            # Send
            await self._send_message()
            
            print(f"✓ Message sent: {text[:50]}...")
            
        except Exception as e:
            print(f"✗ Failed to send message: {e}")
            raise

    async def quick_send(self, text: str) -> None:
        """
        Send message quickly without thinking delay.
        Used for quick responses like "м" or "ж".
        """
        try:
            await self._focus_input()
            await self._type_text(text)
            await self._send_message()
            
            print(f"✓ Quick send: {text}")
            
        except Exception as e:
            print(f"✗ Failed to quick send: {e}")
            raise

    async def leave_chat(self, reason: str = "пока") -> None:
        """Leave chat with optional reason message"""
        if reason:
            await self.send_message(reason)
        
        # Small delay before leaving
        await asyncio.sleep(random.uniform(0.5, 1.0))

    async def wait_and_type(self, text: str, delay: float = 1.0) -> None:
        """Wait specified delay then type message"""
        await asyncio.sleep(delay)
        await self._type_text(text)

    async def is_input_available(self) -> bool:
        """Check if input field is available for typing"""
        try:
            input_field = await self.page.query_selector(SELECTORS["input_field"])
            if not input_field:
                return False
            
            is_enabled = await input_field.is_enabled()
            is_visible = await input_field.is_visible()
            
            return is_enabled and is_visible
            
        except Exception:
            return False

    async def clear_input(self) -> None:
        """Clear the input field"""
        try:
            input_field = await self._get_input_field()
            
            # Select all and delete
            await input_field.press("Control+A")
            await input_field.press("Delete")
            
        except Exception as e:
            print(f"✗ Failed to clear input: {e}")

    async def paste_text(self, text: str) -> None:
        """
        Paste text directly (faster, less human-like).
        Use sparingly to avoid detection.
        """
        try:
            input_field = await self._get_input_field()
            await input_field.fill(text)
            await asyncio.sleep(random.uniform(0.2, 0.4))
            
        except Exception as e:
            print(f"✗ Failed to paste: {e}")
            raise
