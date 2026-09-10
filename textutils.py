"""Преобразование ответа модели в безопасный HTML для Telegram и нарезка длинных сообщений."""
import html
import re

TG_LIMIT = 4000


def md_to_tg_html(text: str) -> str:
    text = html.escape(text, quote=False)
    # блоки кода ```...```
    text = re.sub(r"```(?:\w+)?\n?(.*?)```", lambda m: f"<pre>{m.group(1).strip()}</pre>", text, flags=re.DOTALL)
    # инлайн-код
    text = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", text)
    # **жирный** и __жирный__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)
    # заголовки markdown -> жирная строка
    text = re.sub(r"^\s{0,3}#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)
    # маркеры списков "- " / "* " -> "• "
    text = re.sub(r"^(\s*)[-*]\s+", r"\1• ", text, flags=re.MULTILINE)
    return text


def strip_markdown(text: str) -> str:
    text = re.sub(r"```(?:\w+)?\n?(.*?)```", r"\1", text, flags=re.DOTALL)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)
    return text


def split_message(text: str, limit: int = TG_LIMIT) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for paragraph in text.split("\n"):
        while len(paragraph) > limit:  # очень длинная строка без переносов
            if current:
                chunks.append(current)
                current = ""
            chunks.append(paragraph[:limit])
            paragraph = paragraph[limit:]
        if len(current) + len(paragraph) + 1 > limit:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}" if current else paragraph
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]
