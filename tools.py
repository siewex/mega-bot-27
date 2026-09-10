"""Инструменты, которые модель может вызывать сама (function calling)."""
import json
import logging

import aiohttp

log = logging.getLogger(__name__)

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Поиск в интернете свежей информации: рейтинги игроков и команд Madden 27, обновления рейтингов, "
            "патчи и изменения геймплея, новости НФЛ (трейды, травмы, результаты). "
            "НЕ используй для вопросов по регламенту лиги MEGA — он есть в системных инструкциях. "
            "Запросы лучше писать на английском, коротко."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Поисковый запрос, например 'Madden 27 ratings update week 2'"},
            },
            "required": ["query"],
        },
    },
}


class ToolRunner:
    def __init__(self, tavily_api_key: str, max_results: int = 5, timeout: int = 25):
        self.tavily_api_key = tavily_api_key
        self.max_results = max_results
        self.timeout = aiohttp.ClientTimeout(total=timeout)

    @property
    def tools(self) -> list[dict]:
        return [WEB_SEARCH_TOOL] if self.tavily_api_key else []

    async def run(self, name: str, arguments: str) -> str:
        try:
            args = json.loads(arguments or "{}")
        except json.JSONDecodeError:
            return "Ошибка: аргументы инструмента не в формате JSON."
        if name == "web_search":
            return await self.web_search(str(args.get("query", "")).strip())
        return f"Неизвестный инструмент: {name}"

    async def web_search(self, query: str) -> str:
        if not query:
            return "Пустой поисковый запрос."
        log.info("web_search: %s", query)
        payload = {"query": query, "max_results": self.max_results, "search_depth": "basic", "include_answer": False}
        headers = {"Authorization": f"Bearer {self.tavily_api_key}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession(timeout=self.timeout) as s:
                async with s.post("https://api.tavily.com/search", json=payload, headers=headers) as r:
                    if r.status != 200:
                        text = await r.text()
                        log.warning("Tavily HTTP %s: %s", r.status, text[:300])
                        return f"Поиск недоступен (HTTP {r.status})."
                    data = await r.json(content_type=None)
        except Exception as e:
            log.warning("Tavily error: %s", e)
            return "Поиск сейчас недоступен."

        results = data.get("results") or []
        if not results:
            return "Ничего не найдено."
        lines = []
        for i, item in enumerate(results[: self.max_results], 1):
            content = (item.get("content") or "").strip().replace("\n", " ")
            lines.append(f"[{i}] {item.get('title', '')}\n{item.get('url', '')}\n{content[:800]}")
        return "Результаты поиска (могут быть неточными, сверяй даты):\n\n" + "\n\n".join(lines)
