"""Клиент OpenAI-совместимого API (chat/completions) на aiohttp — без тяжёлых SDK."""
import asyncio
import logging
import re

import aiohttp

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        fallback_model: str = "",
        reasoning_effort: str = "",
        temperature: float | None = None,
        max_tokens: int = 1500,
        timeout: int = 90,
        max_concurrent: int = 4,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.reasoning_effort = reasoning_effort
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._sem = asyncio.Semaphore(max_concurrent)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            )
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _post(self, payload: dict) -> tuple[int, dict | str]:
        session = await self._get_session()
        async with session.post(self.url, json=payload) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = await resp.text()
            return resp.status, data

    @staticmethod
    def _extract_text(data: dict) -> str:
        try:
            msg = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"Неожиданный ответ API: {str(data)[:300]}")
        content = msg.get("content") or ""
        if isinstance(content, list):  # некоторые прокси отдают content частями
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        content = _THINK_RE.sub("", content).strip()
        return content

    async def _complete_with_model(self, model: str, messages: list[dict]) -> str:
        payload: dict = {"model": model, "messages": messages, "max_tokens": self.max_tokens}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        status, data = await self._post(payload)

        # Часть моделей не принимает temperature/reasoning_effort — пробуем ещё раз «голым» запросом
        if status == 400 and ("temperature" in payload or "reasoning_effort" in payload):
            log.warning("API вернул 400 для %s, повтор без доп. параметров: %s", model, str(data)[:300])
            payload.pop("temperature", None)
            payload.pop("reasoning_effort", None)
            status, data = await self._post(payload)

        if status == 429 or status >= 500:
            await asyncio.sleep(2)
            status, data = await self._post(payload)

        if status != 200:
            raise LLMError(f"HTTP {status}: {str(data)[:300]}")
        if not isinstance(data, dict):
            raise LLMError(f"Ответ не JSON: {str(data)[:300]}")

        text = self._extract_text(data)
        if not text:
            finish = (data.get("choices") or [{}])[0].get("finish_reason")
            raise LLMError(f"Пустой ответ модели (finish_reason={finish}). Возможно, мало MAX_TOKENS.")
        usage = data.get("usage") or {}
        log.info(
            "LLM %s ok: prompt=%s completion=%s",
            model, usage.get("prompt_tokens"), usage.get("completion_tokens"),
        )
        return text

    async def complete(self, messages: list[dict]) -> str:
        async with self._sem:
            try:
                return await self._complete_with_model(self.model, messages)
            except (LLMError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                if not self.fallback_model or self.fallback_model == self.model:
                    raise LLMError(str(e)) from e
                log.warning("Основная модель %s упала (%s), пробую %s", self.model, e, self.fallback_model)
                try:
                    return await self._complete_with_model(self.fallback_model, messages)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e2:
                    raise LLMError(str(e2)) from e2
