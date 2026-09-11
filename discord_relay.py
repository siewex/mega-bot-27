"""Слушает канал Discord, куда MTFranchiseBot постит уведомления, и прокидывает текст наружу."""
import logging
from typing import Awaitable, Callable

import discord

log = logging.getLogger(__name__)

MessageHandler = Callable[[str], Awaitable[None]]


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
        if message.channel.id != self.channel_id:
            return
        if self.source_bot_id is not None and message.author.id != self.source_bot_id:
            return
        text = extract_text(message)
        if not text:
            return
        log.info("Получено сообщение из канала-источника: %s", text[:200].replace("\n", " | "))
        try:
            await self.on_recap(text)
        except Exception:
            log.exception("Ошибка обработки recap-сообщения")
