import asyncio
import json
import os
from typing import Any, Dict

import httpx

from classifier import build_classify_result, parse_model_json
from prompt import SYSTEM_PROMPT
from llm_client import LLMClient

OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")


class OllamaClient(LLMClient):
    def __init__(self):
        self._status: Dict[str, Any] = {
            "ready": False,
            "state": "starting",
            "progress": "",
            "error": "",
            "model": OLLAMA_MODEL,
            "provider": "ollama",
        }
        self._host = OLLAMA_HOST
        self._model = OLLAMA_MODEL

    @property
    def status(self) -> Dict[str, Any]:
        return self._status

    async def ensure_model(self) -> None:
        self._status.update(state="waiting_ollama", ready=False, error="")
        timeout = httpx.Timeout(None)
        async with httpx.AsyncClient(timeout=timeout) as client:
            await self._wait_for_ollama(client)
            tags = (await client.get(f"{self._host}/api/tags")).json()
            if self._model in self._model_names(tags):
                self._status.update(state="ready", ready=True, progress="")
                return

            self._status.update(state="downloading", progress="скачивание модели…")
            async with client.stream(
                "POST",
                f"{self._host}/api/pull",
                json={"name": self._model, "stream": True},
            ) as stream:
                stream.raise_for_status()
                async for line in stream.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    status = chunk.get("status") or ""
                    total = chunk.get("total") or 0
                    done = chunk.get("completed") or 0
                    if total:
                        pct = int(done * 100 / total)
                        self._status["progress"] = f"{status} {pct}%"
                    else:
                        self._status["progress"] = status
                    if status == "success":
                        break

        self._status.update(state="ready", ready=True, progress="", error="")

    async def _wait_for_ollama(self, client: httpx.AsyncClient) -> None:
        last_error = ""
        for _ in range(60):
            try:
                response = await client.get(f"{self._host}/api/tags")
                response.raise_for_status()
                return
            except Exception as exc:
                last_error = str(exc)
                await asyncio.sleep(2)
        raise RuntimeError(f"Ollama не отвечает: {last_error}")

    def _model_names(self, payload: dict) -> set:
        names = set()
        for item in payload.get("models") or []:
            name = item.get("name") or ""
            names.add(name)
            names.add(name.split(":")[0])
        return names

    async def classify_text(self, text: str) -> Dict[str, Any]:
        if not self._status.get("ready"):
            raise RuntimeError("Модель ещё не готова")

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Текст акта ГУ-23:\n\n{text[:16000]}"},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0, "num_predict": 1024, "num_ctx": 4096},
        }
        async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, read=600.0)) as client:
            response = await client.post(f"{self._host}/api/chat", json=payload)
            response.raise_for_status()
            body = response.json()

        raw = ((body.get("message") or {}).get("content")) or ""
        parsed = parse_model_json(raw)
        return build_classify_result(parsed, self._model)
