from abc import ABC, abstractmethod
from typing import Any, Dict
import os

class LLMClient(ABC):
    @abstractmethod
    async def ensure_model(self) -> None:
        """Подготовить модель к работе (скачать, проверить доступность и т.п.)"""
        pass

    @abstractmethod
    async def classify_text(self, text: str) -> Dict[str, Any]:
        """Выполнить классификацию текста, вернуть словарь с полями:
        ok, decision, reply_text, extracted, debug и т.д."""
        pass

    @property
    @abstractmethod
    def status(self) -> Dict[str, Any]:
        """Текущий статус: ready, state, error, model и т.д."""
        pass

def create_llm_client() -> LLMClient:
    provider = os.environ.get("LLM_PROVIDER", "gigachat").lower()
    if provider == "gigachat":
        from gigachat_client import GigaChatClient   # абсолютный импорт
        return GigaChatClient()
    else:
        from ollama_client import OllamaClient       # абсолютный импорт
        return OllamaClient()