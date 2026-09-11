"""Слушает канал Discord, куда MTFranchiseBot постит уведомления, и прокидывает текст наружу.

MTFranchiseBot присылает сообщения в формате Discord "Components V2" (карточки из
компонентов, а не старые embed'ы). Установленная версия discord.py не разбирает такие
компоненты в message.components (получается пустой список несмотря на то, что в
самом Discord карточка видна), поэтому текст достаём из сырого payload шлюза через
on_socket_response — туда попадает JSON именно в том виде, в котором его прислал
Discord, независимо от того, что умеет модель Message конкретной версии библиотеки.
"""
import json
import logging
from typing import Awaitable, Callable

import discord

log = logging.getLogger(__name__)

MessageHandler = Callable[[str], Awaitable[None]]


def _walk_component_text(obj) -> list[str]:
    """Рекурсивно достаёт текстовые поля ("content") из дерева компонентов Discord."""
    texts: list[str] = []
    if isinstance(obj, dict):
        content = obj.get("content")
        if isinstance(content, str) and content.strip():
            texts.append(content)
        for key in ("components", "children"):
            for child in obj.get(key) or []:
                texts.extend(_walk_component_text(child))
        accessory = obj.get("accessory")
        if accessory:
            texts.extend(_walk_component_text(accessory))
    elif isinstance(obj, (list, tuple)):
        for item in obj:
            texts.extend(_walk_component_text(item))
    return texts


def extract_text_from_raw(data: dict) -> str:
    parts = [data.get("content") or ""]
    for embed in data.get("embeds") or []:
        if embed.get("title"):
            parts.append(embed["title"])
        if embed.get("description"):
            parts.append(embed["description"])
        for field in embed.get("fields") or []:
            parts.append(f"{field.get('name', '')}\n{field.get('value', '')}")
        footer = embed.get("footer") or {}
        if footer.get("text"):
            parts.append(footer["text"])
    parts.extend(_walk_component_text(data.get("components") or []))
    return "\n\n".join(p for p in parts if p).strip()


class RecapRelayClient(discord.Client):
    def __init__(self, channel_id: int, source_bot_id: int | None, on_recap: MessageHandler):
        intents = discord.Intents.default()
        intents.message_content = True
        # on_socket_response по умолчанию отключён в discord.py ради производительности —
        # без этого флага он никогда не вызывается.
        super().__init__(intents=intents, enable_debug_events=True)
        self.channel_id = channel_id
        self.source_bot_id = source_bot_id
        self.on_recap = on_recap

    async def on_ready(self) -> None:
        log.info("Discord-relay подключён как %s", self.user)

    async def on_socket_response(self, msg: dict) -> None:
        if msg.get("t") != "MESSAGE_CREATE":
            return
        data = msg.get("d") or {}

        try:
            channel_id = int(data.get("channel_id") or 0)
        except (TypeError, ValueError):
            return
        if channel_id != self.channel_id:
            return

        author = data.get("author") or {}
        try:
            author_id = int(author.get("id") or 0)
        except (TypeError, ValueError):
            author_id = 0
        if self.source_bot_id is not None and author_id != self.source_bot_id:
            return

        text = extract_text_from_raw(data)
        log.info(
            "MESSAGE_CREATE в целевом канале: author=%s content_len=%s components_len=%s -> text_len=%s",
            author.get("username"), len(data.get("content") or ""),
            len(data.get("components") or []), len(text),
        )
        if not text:
            log.warning("Не удалось извлечь текст из payload: %s", json.dumps(data, ensure_ascii=False)[:2000])
            return

        log.info("Получено сообщение из канала-источника: %s", text[:200].replace("\n", " | "))
        try:
            await self.on_recap(text)
        except Exception:
            log.exception("Ошибка обработки recap-сообщения")
