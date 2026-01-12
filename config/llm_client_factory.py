from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any

from config.gemini_client import GeminiClient
from config.openai_client import OpenAIClient


class LLMProvider(str, Enum):
    GEMINI = "gemini"
    OPENAI = "openai"

class LLMClientFactory:
    """
    외부에서 factory 함수를 주입받던 것을,
    provider(enum) 기반으로 내부에서 생성하도록 캡슐화한 클래스.

    핵심:
    - 병렬 스레드에서 안전하게 사용하려고 "매 호출마다 새 client 인스턴스"를 만들게 설계.
    """

    def __init__(self, provider: LLMProvider):
        self.provider = provider

    def create(self) -> Any:
        """
        provider에 따라 적절한 LLM client 인스턴스를 생성해서 반환.
        반환 객체는 generate_json(system_prompt, user_prompt) 메서드를 가진다고 가정.
        """
        if self.provider == LLMProvider.GEMINI:
            # 프로젝트 구조에 맞춰 import 경로는 조정해줘
            return GeminiClient()

        if self.provider == LLMProvider.OPENAI:
            return OpenAIClient()

        raise ValueError(f"Unsupported provider: {self.provider}")