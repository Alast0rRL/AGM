"""Observer Module - Page monitoring and message detection"""

import asyncio
from typing import List, Dict, Optional
from playwright.async_api import Page

from config import SELECTORS


class Message:
    """Represents a chat message"""
    def __init__(self, role: str, content: str, timestamp: float):
        self.role = role  # "own" or "other"
        self.content = content
        self.timestamp = timestamp

    def to_dict(self) -> Dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }


class Observer:
    """
    Monitors Nekto.me page state and detects messages.
    Scans DOM every 500ms for new content.
    """

    def __init__(self, page: Page):
        self.page = page
        self.seen_messages: set = set()
        self.last_message_id: int = 0

    async def _get_message_elements(self, selector: str) -> List:
        """Get all message elements matching selector"""
        try:
            elements = await self.page.query_selector_all(selector)
            return elements
        except Exception:
            return []

    async def _extract_message_text(self, element) -> Optional[str]:
        """Extract text content from message element"""
        try:
            text = await element.text_content()
            return text.strip() if text else None
        except Exception:
            return None

    async def _get_message_id(self, element) -> int:
        """Generate unique ID for message based on content"""
        text = await self._extract_message_text(element)
        return hash(text) if text else 0

    async def get_new_messages(self) -> List[Dict]:
        """
        Scan for new messages since last check.
        Returns list of message dicts with role and content.
        """
        import time

        new_messages = []

        # Get all message elements
        try:
            all_messages = await self.page.query_selector_all(
                f"{SELECTORS['incoming_msg']}, {SELECTORS['outgoing_msg']}"
            )
        except Exception as e:
            print(f"  [Observer] Ошибка поиска сообщений: {e}")
            return new_messages

        for msg_element in all_messages:
            msg_id = await self._get_message_id(msg_element)

            # Skip already seen messages
            if msg_id in self.seen_messages:
                continue

            # Determine message role
            is_outgoing = await self._is_outgoing_message(msg_element)
            role = "own" if is_outgoing else "other"

            # Extract content
            content = await self._extract_message_text(msg_element)

            # Skip system messages and empty content
            if not content or self._is_system_message(content):
                self.seen_messages.add(msg_id)
                continue

            # Create message record
            msg_data = {
                "role": role,
                "content": content,
                "timestamp": time.time()
            }

            new_messages.append(msg_data)
            self.seen_messages.add(msg_id)
            self.last_message_id = msg_id

        if new_messages:
            print(f"  [Observer] Найдено новых сообщений: {len(new_messages)}")

        return new_messages

    async def _is_outgoing_message(self, element) -> bool:
        """Check if message is outgoing (from us)"""
        try:
            # Check for outgoing message class
            classes = await element.get_attribute("class")
            if classes:
                # Nekto.me uses "self" for own messages
                if "self" in classes.lower():
                    return True
                if "nekto" in classes.lower():
                    return False
        except Exception:
            pass
        
        return False

    def _is_system_message(self, text: str) -> bool:
        """Check if message is a system notification"""
        system_patterns = [
            "собеседник найден",
            "собеседник найден",
            "чат завершен",
            "собеседник покинул чат",
            "напишите сообщение",
            "begin typing",
        ]
        
        text_lower = text.lower()
        return any(pattern in text_lower for pattern in system_patterns)

    async def is_chat_ended(self) -> bool:
        """Detect if interlocutor has ended the chat"""
        try:
            # Check for chat ended indicator
            ended_indicator = await self.page.query_selector(
                SELECTORS["chat_ended_indicator"]
            )
            if ended_indicator:
                return True
            
            # Check for new chat button visibility (appears after disconnect)
            new_chat_btn = await self.page.query_selector(
                SELECTORS["new_chat_button"]
            )
            if new_chat_btn:
                is_visible = await new_chat_btn.is_visible()
                if is_visible:
                    return True
            
            return False
        except Exception:
            return False

    async def is_input_ready(self) -> bool:
        """Check if input field is ready for typing"""
        try:
            input_field = await self.page.query_selector(SELECTORS["input_field"])
            if not input_field:
                return False
            
            is_enabled = await input_field.is_enabled()
            is_visible = await input_field.is_visible()
            
            return is_enabled and is_visible
        except Exception:
            return False

    async def wait_for_message(self, timeout: float = 30.0) -> Optional[Dict]:
        """Wait for a new incoming message with timeout"""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            messages = await self.get_new_messages()
            
            for msg in messages:
                if msg["role"] == "other":
                    return msg
            
            await asyncio.sleep(0.5)
        
        return None

    async def get_page_state(self) -> Dict:
        """Get current page state summary"""
        return {
            "chat_ended": await self.is_chat_ended(),
            "input_ready": await self.is_input_ready(),
            "url": self.page.url,
        }

    def clear_history(self) -> None:
        """Clear seen messages history (for new chat)"""
        self.seen_messages.clear()
        self.last_message_id = 0
