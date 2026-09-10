"""Клиент OpenAI-совместимого API (chat/completions) на aiohttp — без тяжёлых SDK.
Поддерживает вызов инструментов (web_search) и запасную модель."""
import asyncio
import logging
import re
from typing import Awaitable, Callable

import aiohttp

log = logging.getLogger(__name__)

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

ToolExecutor = Callable[[str, str], Awaitable[str]]


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
        max_tool_rounds: int = 2,
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.api_key = api_key
        self.model = model
        self.fallback_model = fallback_model
        self.reasoning_effort = reasoning_effort
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tool_rounds = max_tool_rounds
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._sem = asyncio.Semaphore(max_concurrent)
        self._session: aiohttp.ClientSession | None = None
        self._tools_unsupported: set[str] = set()  # модели, которые отвергли tools

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

    async def _post_with_degrade(self, payload: dict, model: str) -> dict:
        """Отправка с понижением: если 400 — убираем temperature/reasoning, потом tools."""
        status, data = await self._post(payload)

        if status == 400 and ("temperature" in payload or "reasoning_effort" in payload):
            log.warning("400 для %s, повтор без temperature/reasoning: %s", model, str(data)[:300])
            payload.pop("temperature", None)
            payload.pop("reasoning_effort", None)
            status, data = await self._post(payload)

        if status == 400 and "tools" in payload:
            log.warning("400 для %s, повтор без инструментов: %s", model, str(data)[:300])
            self._tools_unsupported.add(model)
            payload.pop("tools", None)
            payload.pop("tool_choice", None)
            # из истории убираем служебные сообщения инструментов
            payload["messages"] = [
                m for m in payload["messages"] if m.get("role") != "tool" and not m.get("tool_calls")
            ]
            status, data = await self._post(payload)

        if status == 429 or status >= 500:
            await asyncio.sleep(2)
            status, data = await self._post(payload)

        if status != 200:
            raise LLMError(f"HTTP {status}: {str(data)[:300]}")
        if not isinstance(data, dict):
            raise LLMError(f"Ответ не JSON: {str(data)[:300]}")
        return data

    @staticmethod
    def _message(data: dict) -> dict:
        try:
            return data["choices"][0]["message"] or {}
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"Неожиданный ответ API: {str(data)[:300]}")

    @staticmethod
    def _text(msg: dict) -> str:
        content = msg.get("content") or ""
        if isinstance(content, list):  # некоторые прокси отдают content частями
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        return _THINK_RE.sub("", content).strip()

    async def _complete_with_model(
        self, model: str, messages: list[dict], tools: list[dict] | None, executor: ToolExecutor | None
    ) -> str:
        history = list(messages)
        use_tools = bool(tools and executor and model not in self._tools_unsupported)

        for round_no in range(self.max_tool_rounds + 1):
            payload: dict = {"model": model, "messages": history, "max_tokens": self.max_tokens}
            if self.temperature is not None:
                payload["temperature"] = self.temperature
            if self.reasoning_effort:
                payload["reasoning_effort"] = self.reasoning_effort
            if use_tools:
                payload["tools"] = tools
                # на последнем круге просим ответить без новых поисков
                payload["tool_choice"] = "auto" if round_no < self.max_tool_rounds else "none"

            data = await self._post_with_degrade(payload, model)
            if "tools" not in payload:
                use_tools = False
            history = payload["messages"]
            msg = self._message(data)
            usage = data.get("usage") or {}
            log.info("LLM %s: prompt=%s completion=%s", model, usage.get("prompt_tokens"), usage.get("completion_tokens"))

            tool_calls = msg.get("tool_calls") or []
            if tool_calls and use_tools and executor and round_no < self.max_tool_rounds:
                history = history + [{"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}]
                for call in tool_calls:
                    fn = call.get("function") or {}
                    result = await executor(fn.get("name", ""), fn.get("arguments", "{}"))
                    history.append({"role": "tool", "tool_call_id": call.get("id", ""), "content": result})
                continue

            text = self._text(msg)
            if text:
                return text
            finish = (data.get("choices") or [{}])[0].get("finish_reason")
            raise LLMError(f"Пустой ответ модели (finish_reason={finish}). Возможно, мало MAX_TOKENS.")

        raise LLMError("Модель зациклилась на вызове инструментов.")

    async def complete(
        self, messages: list[dict], tools: list[dict] | None = None, executor: ToolExecutor | None = None
    ) -> str:
        async with self._sem:
            try:
                return await self._complete_with_model(self.model, messages, tools, executor)
            except (LLMError, aiohttp.ClientError, asyncio.TimeoutError) as e:
                if not self.fallback_model or self.fallback_model == self.model:
                    raise LLMError(str(e)) from e
                log.warning("Основная модель %s упала (%s), пробую %s", self.model, e, self.fallback_model)
                try:
                    return await self._complete_with_model(self.fallback_model, messages, tools, executor)
                except (aiohttp.ClientError, asyncio.TimeoutError) as e2:
                    raise LLMError(str(e2)) from e2
