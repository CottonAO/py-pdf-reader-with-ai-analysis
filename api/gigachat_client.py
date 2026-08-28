import os
import json
import uuid
import time
from typing import Any, Dict, Optional

import httpx

from classifier import CATEGORIES, CATEGORY_DECISION, REPLIES
from prompt import SYSTEM_PROMPT
from llm_client import LLMClient

class GigaChatClient(LLMClient):
    def __init__(self):
        self.auth_key = os.environ.get("GIGACHAT_AUTH_KEY")
        if not self.auth_key:
            raise ValueError("GIGACHAT_AUTH_KEY не задан (Basic-ключ для OAuth)")

        self.model = os.environ.get("GIGACHAT_MODEL", "GigaChat-Pro")
        self.api_base = os.environ.get("GIGACHAT_API_BASE", "https://api.giga.chat")
        self.oauth_url = os.environ.get("GIGACHAT_OAUTH_URL",
                                        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
        # Для отладки можно выключить проверку SSL через переменную
        self.verify_ssl = os.environ.get("GIGACHAT_VERIFY_SSL", "false").lower() == "true"

        self._status: Dict[str, Any] = {
            "ready": False,
            "state": "initializing",
            "progress": "",
            "error": "",
            "model": self.model,
        }
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

    @property
    def status(self) -> Dict[str, Any]:
        return self._status

    async def _get_access_token(self) -> str:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.auth_key}",
        }
        data = {"scope": "GIGACHAT_API_PERS"}

        # Отключаем проверку SSL, если не задано иное
        async with httpx.AsyncClient(timeout=60.0, verify=self.verify_ssl) as client:
            response = await client.post(self.oauth_url, headers=headers, data=data)
            response.raise_for_status()
            token_data = response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise RuntimeError(f"Не получен access_token: {token_data}")
            expires_in = token_data.get("expires_at", 30 * 60)
            self._token_expires_at = time.time() + expires_in
            return access_token

    async def _ensure_valid_token(self) -> str:
        if self._access_token is None or time.time() >= self._token_expires_at - 60:
            self._access_token = await self._get_access_token()
        return self._access_token

    async def ensure_model(self) -> None:
        try:
            token = await self._ensure_valid_token()
            url = f"{self.api_base}/v1/models"
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
            async with httpx.AsyncClient(timeout=30.0, verify=self.verify_ssl) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
            self._status.update(state="ready", ready=True, progress="", error="")
        except Exception as e:
            self._status.update(state="error", ready=False, error=str(e))
            raise

    async def classify_text(self, text: str) -> Dict[str, Any]:
        if not self._status["ready"]:
            raise RuntimeError("Модель GigaChat не готова")

        token = await self._ensure_valid_token()

        url = f"{self.api_base}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "model": "GigaChat-3-Ultra",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Текст акта ГУ-23:\n\n{text[:16000]}"},
            ],
            "temperature": 0,
            "max_tokens": 1024,
            # "response_format": {"type": "json_object"},  # <-- Закомментировали
        }

        try:
            async with httpx.AsyncClient(timeout=120.0, verify=self.verify_ssl) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                raw = result["choices"][0]["message"]["content"]
                parsed = json.loads(raw)
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "debug": {"model": self.model}
            }

        category = str(parsed.get("category") or "unknown").strip()
        if category not in CATEGORIES:
            category = "unknown"

        decision = CATEGORY_DECISION[category]
        wagons = parsed.get("wagons") or []
        if not isinstance(wagons, list):
            wagons = [str(wagons)]

        return {
            "ok": True,
            "decision": decision,
            "reply_text": REPLIES[decision],
            "needs_ocr": False,
            "extracted": {
                "legal_entity": str(parsed.get("legal_entity") or ""),
                "station": str(parsed.get("station") or ""),
                "act_number": str(parsed.get("act_number") or ""),
                "act_date": str(parsed.get("act_date") or ""),
                "wagons": [str(item) for item in wagons if item],
                "reason_quote": str(parsed.get("reason_quote") or ""),
            },
            "debug": {
                "category": category,
                "confidence": str(parsed.get("confidence") or "low"),
                "act_form": str(parsed.get("act_form") or "unknown"),
                "location": str(parsed.get("location") or "unknown"),
                "notes": str(parsed.get("notes") or ""),
                "model": self.model,
            },
        }