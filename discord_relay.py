"""Слушает канал Discord, куда MTFranchiseBot постит уведомления, и прокидывает текст наружу."""
import json
import logging
from typing import Awaitable, Callable

import discord

log = logging.getLogger(__name__)

MessageHandler = Callable[[str], Awaitable[None]]


def _component_to_dict(component) -> dict | str:
    if hasattr(component, "to_dict"):
        try:
            return component.to_dict()
        except Exception:
            pass
    return repr(component)


def _walk_component_text(obj) -> list[str]:
    """Рекурсивно достаёт текстовые поля ("content") из дерева компонентов Discord
    (используется в новом формате сообщений Components V2, которым пользуется MTFranchiseBot)."""
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


def extract_text(message: discord.Message) -> str:
    parts = [message.content or ""]
    for embed in message.embeds:
        if embed.title:
            parts.append(embed.title)
        if embed.description:
            parts.append(embed.description)
        for field in embed.fields:
            parts.append(f"{field.name}\n{field.value}")
        if embed.footer and embed.footer.text:
            parts.append(embed.footer.text)
    for component in message.components:
        parts.extend(_walk_component_text(_component_to_dict(component)))
    return "\n\n".join(p for p in parts if p).strip()


class RecapRelayClient(discord.Client):
    def __init__(self, channel_id: int, source_bot_id: int | None, on_recap: MessageHandler):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.channel_id = channel_id
        self.source_bot_id = source_bot_id
        self.on_recap = on_recap

    async def on_ready(self) -> None:
        log.info("Discord-relay подключён как %s", self.user)

    async def on_message(self, message: discord.Message) -> None:
        # ВРЕМЕННАЯ диагностика: показать вообще все сообщения, которые видит бот,
        # чтобы свериться с DISCORD_RECAP_CHANNEL_ID / DISCORD_SOURCE_BOT_ID в .env.
        components_dump = json.dumps(
            [_component_to_dict(c) for c in message.components], ensure_ascii=False, default=str
        )
        log.info(
            "on_message: channel_id=%s (нужен %s) author=%s author_id=%s (нужен %s) content_len=%s embeds=%s components=%s",
            message.channel.id, self.channel_id,
            message.author, message.author.id, self.source_bot_id,
            len(message.content or ""), len(message.embeds), components_dump[:2000],
        )

        if message.channel.id != self.channel_id:
            return
        if self.source_bot_id is not None and message.author.id != self.source_bot_id:
            return
        text = extract_text(message)
        if not text:
            log.warning("Сообщение прошло фильтры, но extract_text вернул пусто (content и embeds пустые?)")
            return
        log.info("Получено сообщение из канала-источника: %s", text[:200].replace("\n", " | "))
        try:
            await self.on_recap(text)
        except Exception:
            log.exception("Ошибка обработки recap-сообщения")
