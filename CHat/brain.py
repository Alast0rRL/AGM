"""Brain Module - LLM integration and response generation"""

import httpx
import random
from typing import List, Dict, Optional

from config import (
    LLM_API_URL,
    LLM_MODEL,
    TELEGRAM_USERNAME,
    CONVERSION_KEYWORDS,
    AGGRESSION_KEYWORDS,
    QUICK_RESPONSES,
    POSITIVE_SENTIMENT,
    NEGATIVE_SENTIMENT,
)


class Brain:
    """
    Handles LLM integration for response generation.
    Manages conversation context and prompt engineering.
    """

    def __init__(self):
        self.context: List[Dict[str, str]] = []
        self.system_prompt = self._build_system_prompt()
        self.api_url = LLM_API_URL
        self.model = LLM_MODEL
        self.message_count = 0  # Track for emoji logic

    def _build_system_prompt(self) -> str:
        """Build the system prompt with personality and goals"""
        return f"""ты анонимный собеседник в чате знакомств. твоя задача:
1. вести непринужденную беседу в стиле lowercase без точек
2. задавать вопросы о собеседнике (имя, возраст, интересы)
3. при достижении симпатии предложить перейти в телеграм

правила стиля:
- только строчные буквы
- без точек в конце предложений
- короткие сообщения (3-6 слов в среднем)
- эмодзи редко (примерно 1 на 3 сообщения)
- естественная манера общения

телеграм для перехода: @{TELEGRAM_USERNAME}

не пиши длинные тексты, будь лаконичным и интересным"""

    def _get_quick_response(self, message: str) -> Optional[str]:
        """Check for pattern-based quick responses"""
        message_lower = message.lower().strip()
        
        for pattern, response in QUICK_RESPONSES.items():
            if pattern in message_lower:
                return response
        
        return None

    def get_quick_response(self, message: str) -> Optional[str]:
        """Public method for quick responses"""
        return self._get_quick_response(message)

    def detect_aggression(self, message: str) -> bool:
        """Detect aggressive or hostile content"""
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in AGGRESSION_KEYWORDS)

    def is_conversion_message(self, message: str) -> bool:
        """Check if message contains Telegram conversion keywords"""
        message_lower = message.lower()
        
        # Check for Telegram-specific patterns
        tg_patterns = ["@", "тг", "телеграм", "теле", "telegram"]
        if any(pattern in message_lower for pattern in tg_patterns):
            return True
        
        return False

    def _calculate_sympathy_index(self) -> float:
        """
        Calculate sympathy index based on conversation tone.
        Returns value between 0.0 and 1.0
        Uses sentiment analysis for better accuracy.
        """
        if len(self.context) < 2:
            return 0.0

        positive_score = 0
        negative_score = 0

        # Analyze user messages for sentiment
        for msg in self.context:
            if msg["role"] != "user":
                continue

            content = msg["content"].lower()

            # Check positive sentiment
            for keyword in POSITIVE_SENTIMENT:
                if keyword in content:
                    positive_score += 1
                    break

            # Check negative sentiment
            for keyword in NEGATIVE_SENTIMENT:
                if keyword in content:
                    negative_score += 1
                    break

        # Calculate net sentiment ratio
        total = positive_score + negative_score
        if total == 0:
            return 0.5  # Neutral if no sentiment detected

        # Weighted score: positive interactions matter more
        raw_ratio = positive_score / total

        # Boost based on conversation length (more messages = more trust)
        length_bonus = min(len(self.context) / 20, 0.2)

        return min(raw_ratio + length_bonus, 1.0)

    def should_convert(self) -> bool:
        """Determine if it's time to suggest Telegram"""
        sympathy = self._calculate_sympathy_index()
        
        # Convert after 6+ messages with good sympathy
        if len(self.context) >= 6 and sympathy >= 0.3:
            return True
        
        # Force convert after many messages
        if len(self.context) >= 12:
            return True
        
        return False

    def add_to_context(self, role: str, content: str) -> None:
        """Add message to conversation context"""
        self.context.append({
            "role": role,
            "content": content
        })
        
        # Limit context length to avoid token overflow
        if len(self.context) > 20:
            self.context = self.context[-20:]

    def clear_context(self) -> None:
        """Clear conversation context for new chat"""
        self.context = []
        self.message_count = 0

    async def generate_response(self, incoming_message: str) -> Optional[str]:
        """
        Generate response using LLM.
        Handles API errors gracefully.
        """
        # Add incoming message to context
        self.add_to_context("user", incoming_message)
        
        # Check if we should convert to Telegram
        if self.should_convert():
            conversion_msg = f"слушай, тут чат лагает часто, го в тг? @{TELEGRAM_USERNAME}"
            self.add_to_context("assistant", conversion_msg)
            return conversion_msg
        
        # Build prompt messages
        messages = [
            {"role": "system", "content": self.system_prompt},
        ] + self.context
        
        try:
            response = await self._call_llm(messages)
            
            if response:
                # Format response (lowercase, no trailing dots)
                formatted = self._format_response(response)
                self.add_to_context("assistant", formatted)
                return formatted
            else:
                return None
                
        except Exception as e:
            print(f"LLM API error: {e}")
            # Fallback response
            fallback = "ща, чет инет тупит"
            return fallback

    async def _call_llm(self, messages: List[Dict]) -> Optional[str]:
        """Call LLM API and get response"""
        
        # Build prompt text from messages
        prompt = self._messages_to_prompt(messages)
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.8,
                "top_p": 0.9,
                "max_tokens": 100,
            }
        }
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.post(
                    self.api_url,
                    json=payload
                )
                response.raise_for_status()
                
                data = response.json()
                text = data.get("response", "").strip()
                
                return text if text else None
                
            except httpx.TimeoutException:
                print("LLM API timeout")
                return None
            except httpx.ConnectError:
                print("Cannot connect to LLM API - is Ollama running?")
                return None
            except Exception as e:
                print(f"LLM API error: {e}")
                return None

    def _messages_to_prompt(self, messages: List[Dict]) -> str:
        """Convert message list to prompt format for Qwen"""
        prompt_parts = []
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "system":
                prompt_parts.append(f"<|system|>\n{content}")
            elif role == "user":
                prompt_parts.append(f"<|user|>\n{content}")
            elif role == "assistant":
                prompt_parts.append(f"<|assistant|>\n{content}")
        
        prompt_parts.append("<|assistant|>\n")
        
        return "\n".join(prompt_parts)

    def _format_response(self, text: str) -> str:
        """
        Format response to match desired style:
        - lowercase
        - no trailing dots
        - minimal punctuation
        - emoji every ~3 messages
        """
        # Convert to lowercase
        formatted = text.lower()

        # Remove trailing dots and spaces
        formatted = formatted.rstrip(". ").strip()

        # Add emoji every ~3 messages (30% chance)
        if random.random() < 0.33:
            emoji = random.choice(["😊", "😄", "👍", "✨", "😅", "🤔", "💯"])
            formatted = formatted + " " + emoji

        # Limit length (keep it conversational)
        if len(formatted) > 150:
            formatted = formatted[:147] + "..."

        self.message_count += 1

        return formatted

    def get_context_summary(self) -> Dict:
        """Get current context summary"""
        return {
            "message_count": len(self.context),
            "sympathy_index": self._calculate_sympathy_index(),
            "should_convert": self.should_convert(),
        }
