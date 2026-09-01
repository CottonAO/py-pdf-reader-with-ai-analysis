import os
import uuid
import time
from typing import Any, Dict, Optional

import httpx

from classifier import build_classify_result, parse_model_json
from prompt import SYSTEM_PROMPT
from llm_client import LLMClient
from security import apply_security_checks, wrap_user_document


def _parse_expires_at(token_data: dict) -> float:
    """expires_at у Сбера — unix в миллисекундах, не длительность."""
    raw = token_data.get("expires_at")
    if raw is None:
        return time.time() + 25 * 60
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return time.time() + 25 * 60
    if value > 10_000_000_000:  # миллисекунды
        return value / 1000.0
    if value > 1_000_000_000:  # уже секунды unix
        return value
    return time.time() + value


class GigaChatClient(LLMClient):
    def __init__(self):
        self.auth_key = (os.environ.get("GIGACHAT_AUTH_KEY") or "").strip()
        self.model = os.environ.get("GIGACHAT_MODEL", "GigaChat-3-Ultra")
        self.scope = os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
        self.api_base = os.environ.get("GIGACHAT_API_BASE", "https://api.giga.chat").rstrip("/")
        self.oauth_url = os.environ.get(
            "GIGACHAT_OAUTH_URL",
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        )
        self.verify_ssl = os.environ.get("GIGACHAT_VERIFY_SSL", "false").lower() == "true"

        self._status: Dict[str, Any] = {
            "ready": False,
            "state": "initializing",
            "progress": "",
            "error": "",
            "model": self.model,
            "provider": "gigachat",
        }
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

        if self.auth_key.lower().startswith("basic "):
            self.auth_key = self.auth_key[6:].strip()
        pad = len(self.auth_key) % 4
        if self.auth_key and pad:
            self.auth_key += "=" * (4 - pad)

        if not self.auth_key:
            self._status.update(
                state="error",
                ready=False,
                error="Задайте GIGACHAT_AUTH_KEY в файле .env",
            )

    @property
    def status(self) -> Dict[str, Any]:
        return self._status

    async def _get_access_token(self) -> str:
        # Сбер отдаёт 400, если в Content-Type есть charset=utf-8 (httpx так делает при data=).
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "RqUID": str(uuid.uuid4()),
            "Authorization": f"Basic {self.auth_key}",
        }
        body = f"scope={self.scope}".encode("ascii")

        async with httpx.AsyncClient(timeout=60.0, verify=self.verify_ssl) as client:
            response = await client.post(self.oauth_url, headers=headers, content=body)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"OAuth {response.status_code}: {(response.text or '')[:500]}"
                )
            token_data = response.json()
            access_token = token_data.get("access_token")
            if not access_token:
                raise RuntimeError(f"Не получен access_token: {token_data}")
            self._token_expires_at = _parse_expires_at(token_data)
            return access_token

    async def _ensure_valid_token(self) -> str:
        if self._access_token is None or time.time() >= self._token_expires_at - 60:
            self._access_token = await self._get_access_token()
        return self._access_token

    async def ensure_model(self) -> None:
        if not self.auth_key:
            return
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
        except Exception as exc:
            self._status.update(state="error", ready=False, error=str(exc))

    async def _chat(self, token: str, text: str) -> httpx.Response:
        url = f"{self.api_base}/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": wrap_user_document(text)},
            ],
            "temperature": 0,
            "max_tokens": 1024,
        }
        async with httpx.AsyncClient(timeout=120.0, verify=self.verify_ssl) as client:
            return await client.post(url, headers=headers, json=payload)

    async def classify_text(self, text: str) -> Dict[str, Any]:
        if not self._status.get("ready"):
            raise RuntimeError(self._status.get("error") or "Модель GigaChat не готова")

        token = await self._ensure_valid_token()
        response = await self._chat(token, text)
        if response.status_code == 401:
            self._access_token = None
            token = await self._ensure_valid_token()
            response = await self._chat(token, text)
        response.raise_for_status()
        body = response.json()
        try:
            raw = body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(f"Неожиданный ответ GigaChat: {body}") from exc
        parsed = parse_model_json(raw)
        result = build_classify_result(parsed, self.model)
        return apply_security_checks(text, result)
