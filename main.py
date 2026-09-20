"""MEGA-бот: помощник лиги Madden 27 в Telegram.

Отвечает, когда его тегают (@username), когда отвечают на его сообщение
или (опционально) по ключевым словам. Ведёт диалог по ветке ответов.
"""
import asyncio
import html
import logging
import os
import re
import time
from datetime import date

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import BotCommand, BufferedInputFile, LinkPreviewOptions, Message, User
from aiogram.utils.chat_action import ChatActionSender

from config import settings
from discord_relay import RecapRelayClient
from llm import LLMClient, LLMError
from prompt import build_system_prompt, load_knowledge
from recap import (
    GameEvent,
    format_remaining_message,
    format_schedule_message,
    format_telegram_message,
    game_key,
    generate_blurb,
    is_final_score_message,
    parse_final_score_messages,
    parse_weekly_board,
    remaining_key,
    schedule_key,
)
from game_schedule import detect_force, find_team_by_telegram, find_game_for_team, format_status_message, format_when, parse_game_time, save_gametime, save_week_games, GameTimeRecord
from recap_state import RecapState
from scorecard import render_scorecard
from storage import MessageStore
from textutils import md_to_tg_html, split_message, strip_markdown
from tools import ToolRunner
from transactions import TransactionEvent, format_transactions_message, is_transactions_message, parse_transactions

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("mega-bot")

router = Router()
store: MessageStore
llm: LLMClient
tools: ToolRunner = ToolRunner("")
KNOWLEDGE = ""
BOT_USER: User | None = None
recap_state: RecapState
recap_handler = None  # заполняется в main(); тот же обработчик, что и у Discord-relay

_last_request: dict[int, float] = {}
_daily: dict[tuple[int, date], int] = {}
_busy: set[int] = set()


# ---------- вспомогательное ----------

def commissioners_hint() -> str:
    return f" ({settings.commissioners})" if settings.commissioners else ""


def is_admin(user_id: int | None) -> bool:
    return user_id is not None and user_id in settings.admin_ids


def author_name(message: Message) -> str:
    if message.sender_chat and message.sender_chat.id == message.chat.id:
        return "Администратор группы"
    user = message.from_user
    if not user:
        return "Участник"
    name = user.full_name or "Участник"
    return f"{name} (@{user.username})" if user.username else name


def message_text(message: Message) -> str:
    return (message.text or message.caption or "").strip()


def real_reply(message: Message) -> Message | None:
    """reply_to_message, но без служебного «топик создан» в форумах."""
    reply = message.reply_to_message
    if reply is None or reply.forum_topic_created is not None:
        return None
    return reply


def is_schedule_post(message: Message | None) -> bool:
    """Пост с расписанием — туда отвечают анонсами матчей, а не вопросами к боту."""
    if message is None:
        return False
    text = message.text or message.caption or ""
    return text.startswith("Расписание · Неделя")


def is_gametime_confirmation(message: Message | None) -> bool:
    """Собственное подтверждение бота ("✅ Записал..."/"⚠️ Записал...") — реплай на него
    тоже должен уходить в трекер времени игр, а не в LLM: так можно поправить время,
    ответив на последнее сообщение в цепочке, а не только на исходное расписание."""
    if message is None:
        return False
    text = message.text or message.caption or ""
    return text.startswith("✅ Записал") or text.startswith("⚠️ Записал")


def is_gametime_related_post(message: Message | None) -> bool:
    return is_schedule_post(message) or is_gametime_confirmation(message)


def mentions_bot(message: Message) -> bool:
    if BOT_USER is None:
        return False
    text = message.text or message.caption or ""
    entities = message.entities or message.caption_entities or []
    username = (BOT_USER.username or "").lower()
    for ent in entities:
        if ent.type == "mention" and username:
            if ent.extract_from(text).lstrip("@").lower() == username:
                return True
        if ent.type == "text_mention" and ent.user and ent.user.id == BOT_USER.id:
            return True
    return False


def strip_bot_mention(text: str) -> str:
    if BOT_USER and BOT_USER.username:
        text = re.sub(rf"@{re.escape(BOT_USER.username)}\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", text).strip(" ,")


def hits_trigger_word(text: str) -> bool:
    low = text.lower()
    return any(re.search(rf"(?<!\w){re.escape(w)}(?!\w)", low) for w in settings.trigger_words)


def chat_allowed(message: Message) -> bool:
    if message.chat.type == "private":
        return settings.allow_private or is_admin(message.from_user.id if message.from_user else None)
    if settings.allowed_chat_ids:
        return message.chat.id in settings.allowed_chat_ids
    return True


def should_respond(message: Message) -> bool:
    if message.from_user and message.from_user.is_bot:
        return False
    if message.is_automatic_forward or message.via_bot:
        return False
    if not message_text(message):
        return False
    if not chat_allowed(message):
        return False
    if message.chat.type == "private":
        return True
    reply = real_reply(message)
    if reply and BOT_USER and reply.from_user and reply.from_user.id == BOT_USER.id and not is_gametime_related_post(reply):
        return True
    if mentions_bot(message):
        return True
    return bool(settings.trigger_words) and hits_trigger_word(message_text(message))


def check_limits(user_id: int) -> str | None:
    if is_admin(user_id):
        return None
    if user_id in _busy:
        return "⏳ Погоди, ещё думаю над прошлым вопросом."
    now = time.monotonic()
    if now - _last_request.get(user_id, 0) < settings.cooldown_seconds:
        return "⏳ Не так быстро, дай пару секунд."
    if settings.daily_limit_per_user > 0:
        key = (user_id, date.today())
        if _daily.get(key, 0) >= settings.daily_limit_per_user:
            return f"На сегодня твой лимит вопросов исчерпан ({settings.daily_limit_per_user}). Завтра продолжим 🙌"
    return None


def register_request(user_id: int) -> None:
    _last_request[user_id] = time.monotonic()
    key = (user_id, date.today())
    _daily[key] = _daily.get(key, 0) + 1
    if len(_daily) > 5000:  # чистим старые дни
        today = date.today()
        for k in [k for k in _daily if k[1] != today]:
            _daily.pop(k, None)


def build_llm_messages(history) -> list[dict]:
    msgs: list[dict] = []
    for m in history:
        if m.role == "assistant":
            role, content = "assistant", m.text
        else:
            role, content = "user", f"[{m.author}]: {m.text}"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n\n" + content
        else:
            msgs.append({"role": role, "content": content})
    if msgs and msgs[0]["role"] == "assistant":
        msgs.insert(0, {"role": "user", "content": "[контекст]: продолжение разговора в чате лиги"})
    system = build_system_prompt(settings.bot_name, settings.commissioners, KNOWLEDGE, bool(tools.tools))
    return [{"role": "system", "content": system}] + msgs


async def send_answer(message: Message, answer: str) -> list[Message]:
    sent: list[Message] = []
    reply_target = message
    for chunk in split_message(answer):
        try:
            msg = await reply_target.reply(
                md_to_tg_html(chunk),
                parse_mode="HTML",
                link_preview_options=LinkPreviewOptions(is_disabled=True),
            )
        except TelegramBadRequest as e:
            log.warning("HTML не прошёл (%s), отправляю простым текстом", e)
            msg = await reply_target.reply(
                strip_markdown(chunk), parse_mode=None, link_preview_options=LinkPreviewOptions(is_disabled=True)
            )
        sent.append(msg)
        reply_target = msg
    return sent


# ---------- команды ----------

HELP_TEXT = (
    "Привет! Я {name} — помощник лиги MEGA по Madden 27 🏈\n\n"
    "<b>Как со мной говорить в группе:</b>\n"
    "• тегни меня: <code>@{username} сколько трейдов можно сделать с одной командой?</code>\n"
    "• чтобы продолжить разговор — просто ответь (reply) на моё сообщение\n"
    "• можно ответить на чужое сообщение и тегнуть меня — я увижу, о чём речь\n\n"
    "<b>Что умею:</b> подсказать по регламенту (с номерами пунктов), объяснить рейтинги и механики Madden 27 "
    "(SPD, ACC, COD, пресс, Smart Zones, Timing Based Catching и т.д.), просто поболтать о футболе.\n\n"
    "Я не комиссионер: трейды не утверждаю и наказания не назначаю. Спорное — к комиссионерам{hint}."
)


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if not chat_allowed(message):
        return
    await message.reply(
        HELP_TEXT.format(
            name=settings.bot_name,
            username=BOT_USER.username if BOT_USER else "bot",
            hint=commissioners_hint(),
        ),
        parse_mode="HTML",
    )


@router.message(Command("rules"))
async def cmd_rules(message: Message) -> None:
    if not chat_allowed(message):
        return
    url = os.getenv("RULES_URL", "").strip()
    text = "📘 Регламент лиги MEGA — у меня в голове целиком, спрашивай любой пункт."
    if url:
        text += f"\nПолный текст: {url}"
    text += "\n\nНапример: «когда можно разыгрывать 4-й даун?» или «что будет за отказ от трейда?»"
    await message.reply(text, link_preview_options=LinkPreviewOptions(is_disabled=True))


@router.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    if message.chat.type == "private":
        store.clear_chat(message.chat.id)
        await message.reply("Начинаем с чистого листа 🧹")
    else:
        await message.reply("В группе контекст — это ветка ответов. Чтобы начать новую тему, просто тегни меня новым сообщением.")


@router.message(Command("id"))
async def cmd_id(message: Message) -> None:
    uid = message.from_user.id if message.from_user else "—"
    await message.reply(f"chat_id: <code>{message.chat.id}</code>\nuser_id: <code>{uid}</code>", parse_mode="HTML")


def _utf16_slice(text: str, offset: int, length: int) -> str:
    """Entity offset/length у Telegram — в UTF-16 code units, не в символах Python."""
    encoded = text.encode("utf-16-le")
    return encoded[offset * 2 : (offset + length) * 2].decode("utf-16-le", errors="ignore")


@router.message(Command("emojiid"))
async def cmd_emojiid(message: Message) -> None:
    """Админская утилита: ответь этой командой на сообщение с премиум/кастомным эмодзи — вернёт его custom_emoji_id."""
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    target = message.reply_to_message
    if not target:
        await message.reply("Ответь этой командой на сообщение с нужным эмодзи.")
        return
    text = target.text or target.caption or ""
    entities = (target.entities or []) + (target.caption_entities or [])
    found = [e for e in entities if e.type == "custom_emoji"]
    if not found:
        await message.reply("В этом сообщении не нашёл кастомных/премиум эмодзи.")
        return
    lines = [f"{_utf16_slice(text, e.offset, e.length)} → <code>{e.custom_emoji_id}</code>" for e in found]
    await message.reply("\n".join(lines), parse_mode="HTML")


TEST_SCHEDULE_GAMES = [
    GameEvent("ТЕСТ", "MIN", "NYG", None, None),
    GameEvent("ТЕСТ", "KC", "BUF", None, None),
    GameEvent("ТЕСТ", "PIT", "CIN", None, None),
]
TEST_RECAP_EVENT = GameEvent(week="", away="MIN", home="NYG", away_score=17, home_score=38)
TEST_TRANSACTIONS = [
    TransactionEvent(team="JAX", type="SIGNING", player="DaQuan Jones"),
    TransactionEvent(team="DET", type="RELEASE", player="Jack Kiser"),
]


@router.message(Command("testschedule"))
async def cmd_testschedule(message: Message) -> None:
    """Админская утилита: пример сообщения с расписанием — уходит в этот же чат, без ожидания реальной недели."""
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    text = format_schedule_message("ТЕСТ", TEST_SCHEDULE_GAMES)
    await message.answer(text, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))


@router.message(Command("testrecap"))
async def cmd_testrecap(message: Message) -> None:
    """Админская утилита: пример GAME RECAP (с реальным хайп-текстом от LLM) — уходит в этот же чат."""
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    try:
        blurb = await generate_blurb(llm, TEST_RECAP_EVENT)
    except LLMError as e:
        await message.answer(f"LLM не ответила: {e}")
        blurb = ""
    text = format_telegram_message(TEST_RECAP_EVENT, md_to_tg_html(blurb) if blurb else "")
    png = render_scorecard(
        TEST_RECAP_EVENT.week, TEST_RECAP_EVENT.away, TEST_RECAP_EVENT.home,
        TEST_RECAP_EVENT.away_score, TEST_RECAP_EVENT.home_score,
    )
    await message.answer_photo(BufferedInputFile(png, filename="scorecard.png"), caption=text, parse_mode="HTML")


@router.message(Command("testtransactions"))
async def cmd_testtransactions(message: Message) -> None:
    """Админская утилита: пример сообщения с трансферами — уходит в этот же чат."""
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    text = format_transactions_message(TEST_TRANSACTIONS)
    await message.answer(text, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))


@router.message(Command("replay"))
async def cmd_replay(message: Message) -> None:
    """Админская утилита: скормить боту произвольный текст так, будто он только что
    прилетел из Discord-канала (например, если relay пропустил часть игр из-за бага —
    после фикса можно вручную вставить исходный текст уведомления и переобработать)."""
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    if recap_handler is None:
        await message.reply("Discord-relay выключен, обрабатывать нечем.")
        return
    parts = message_text(message).split(maxsplit=1)
    if len(parts) < 2:
        await message.reply(
            "Использование: /replay <текст уведомления, как он выглядит в Discord-канале>\n"
            "Например: /replay Final scores\\nNO 14 @ DET 28\\nCLE 17 @ JAX 24"
        )
        return
    await recap_handler(parts[1])
    await message.reply("Обработано (новые игры/расписание уйдут в основной чат, уже показанные — пропустятся).")


@router.message(Command("reload"))
async def cmd_reload(message: Message) -> None:
    global KNOWLEDGE
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    KNOWLEDGE = load_knowledge(settings.knowledge_dir)
    await message.reply(f"🔄 База знаний перечитана: {len(KNOWLEDGE):,} символов.".replace(",", " "))


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    if not is_admin(message.from_user.id if message.from_user else None):
        return
    await message.reply(
        f"Модель: {settings.model}\nЗапасная: {settings.fallback_model or '—'}\n"
        f"Reasoning: {settings.reasoning_effort or '—'}\nБаза знаний: {len(KNOWLEDGE)} симв.\n"
        f"Поиск в интернете: {'вкл' if tools.tools else 'выкл'}\n"
        f"Запросов сегодня: {sum(v for (u, d), v in _daily.items() if d == date.today())}"
    )


@router.message(Command("gametimes"))
async def cmd_gametimes(message: Message) -> None:
    if not chat_allowed(message):
        return
    week = recap_state.get_meta("current_week")
    if not week:
        await message.reply("Пока не знаю расписание текущей недели — дождись, пока бот его пришлёт.")
        return
    text = format_status_message(recap_state, week)
    await message.reply(text, parse_mode="HTML", link_preview_options=LinkPreviewOptions(is_disabled=True))


# ---------- реплаи на пост с расписанием: фиксируем время игры ----------

async def is_schedule_reply(message: Message) -> bool:
    return is_gametime_related_post(real_reply(message))


@router.message(is_schedule_reply)
async def on_schedule_reply(message: Message) -> None:
    week = recap_state.get_meta("current_week")
    if not week:
        return
    user = message.from_user
    text = message_text(message)
    own_team = find_team_by_telegram(user.username if user else None, user.id if user else None)

    forced_team = detect_force(text)
    if forced_team is not None or (own_team and "форс" in text.lower()):
        # "Форс Теннесси" от соперника — команду берём из текста.
        # Просто "форс" от самого владельца — форсуют его текущего соперника по расписанию.
        target_team = forced_team or own_team
        game = find_game_for_team(recap_state, week, target_team)
        if game is None:
            await message.reply("Не нашёл эту игру на этой неделе — свяжись с комиссионерами.")
            return
        away, home = game
        if forced_team is None:
            # own_team форсит — значит форс объявлен против его соперника по игре
            opponent = home if own_team == away else away
        else:
            opponent = forced_team
        save_gametime(recap_state, week, away, home, GameTimeRecord(when_display="", by_user=own_team or "", forced_against=opponent))
        await message.reply(f"⚠️ Записал: {away} — {home}: форс против {opponent}", parse_mode="HTML")
        return

    if own_team is None:
        await message.reply(
            "Не смог понять, за какую команду ты отвечаешь — реплай на расписание пойму только от "
            "владельцев команд из teams_map.py."
        )
        return
    game = find_game_for_team(recap_state, week, own_team)
    if game is None:
        await message.reply("Не нашёл твою игру на этой неделе — странно, свяжись с комиссионерами.")
        return
    away, home = game

    dt = parse_game_time(text)
    when_display = format_when(dt) if dt else html.escape(text[:100], quote=False)
    save_gametime(recap_state, week, away, home, GameTimeRecord(when_display=when_display, by_user=own_team))
    await message.reply(f"✅ Записал: {away} — {home}: {when_display}", parse_mode="HTML")


# ---------- основной обработчик ----------

@router.message(F.text | F.caption)
async def on_message(message: Message) -> None:
    if not should_respond(message):
        return
    if message.text and message.text.startswith("/"):
        return  # незнакомые команды игнорируем

    user_id = message.from_user.id if message.from_user else message.chat.id
    limit_msg = check_limits(user_id)
    if limit_msg:
        await message.reply(limit_msg)
        return

    chat_id = message.chat.id
    text = strip_bot_mention(message_text(message))[: settings.max_question_chars]
    if not text:
        text = "(тегнул тебя без вопроса)"
    if message.quote and message.quote.text:
        text = f"(цитирует: «{message.quote.text}»)\n{text}"

    reply = real_reply(message)
    if reply and not store.get(chat_id, reply.message_id):
        quoted = message_text(reply)
        if quoted:
            parent = real_reply(reply)
            role = "assistant" if (BOT_USER and reply.from_user and reply.from_user.id == BOT_USER.id) else "user"
            store.save(chat_id, reply.message_id, role, author_name(reply), quoted[: settings.max_question_chars],
                       parent.message_id if parent else None)

    store.save(chat_id, message.message_id, "user", author_name(message), text, reply.message_id if reply else None)

    if message.chat.type == "private" and reply is None:
        history = store.recent(chat_id, settings.history_limit)
    else:
        history = store.thread(chat_id, message.message_id, settings.history_limit)

    register_request(user_id)
    _busy.add(user_id)
    try:
        thread_id = message.message_thread_id if message.is_topic_message else None
        async with ChatActionSender.typing(bot=message.bot, chat_id=chat_id, message_thread_id=thread_id):
            answer = await llm.complete(build_llm_messages(history), tools.tools or None, tools.run)
    except LLMError as e:
        log.error("Ошибка LLM: %s", e)
        await message.reply(f"Что-то я подвис 🥲 Попробуй ещё раз чуть позже. Если срочно — пиши комиссионерам{commissioners_hint()}.")
        return
    except Exception:
        log.exception("Непредвиденная ошибка")
        await message.reply("Упс, что-то сломалось. Попробуй ещё раз.")
        return
    finally:
        _busy.discard(user_id)

    sent = await send_answer(message, answer)
    parent_id = message.message_id
    for msg, chunk in zip(sent, split_message(answer)):
        store.save(chat_id, msg.message_id, "assistant", settings.bot_name, chunk, parent_id)
        parent_id = msg.message_id


# ---------- запуск ----------

async def periodic_cleanup() -> None:
    while True:
        try:
            removed = store.cleanup(settings.history_ttl_days)
            if removed:
                log.info("Удалено старых сообщений из истории: %s", removed)
        except Exception:
            log.exception("Ошибка очистки истории")
        await asyncio.sleep(12 * 3600)


def make_recap_handler(bot: Bot):
    state = recap_state  # общий инстанс — нужен и обработчику реплаев на расписание

    async def handle_recap(raw_text: str) -> None:
        if is_transactions_message(raw_text):
            if not settings.transactions_chat_id:
                return
            events = parse_transactions(raw_text)
            if not events:
                log.warning("Сообщение похоже на Transactions, но ни одной строки не разобралось: %s", raw_text[:300])
                return
            new_events = [e for e in events if state.is_new(e.key())]
            if new_events:
                text = format_transactions_message(new_events)
                await bot.send_message(
                    settings.transactions_chat_id, text, parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                for e in new_events:
                    state.mark_seen(e.key())
            return

        if is_final_score_message(raw_text):
            events = parse_final_score_messages(raw_text)
            if not events:
                log.warning("Похоже на Final scores, но не удалось разобрать счёт: %s", raw_text[:300])
                return
            for event in events:
                if not state.is_new(game_key(event)):
                    continue
                try:
                    blurb = await generate_blurb(llm, event)
                except LLMError as e:
                    log.error("LLM не сгенерировала recap (%s), отправляю без хайп-текста", e)
                    blurb = ""
                text = format_telegram_message(event, md_to_tg_html(blurb) if blurb else "")
                png = render_scorecard(event.week, event.away, event.home, event.away_score, event.home_score)
                await bot.send_photo(
                    settings.recap_chat_id,
                    BufferedInputFile(png, filename="scorecard.png"),
                    caption=text, parse_mode="HTML",
                )
                state.mark_seen(game_key(event))
            return

        # Сводка `scores` используется для расписания — recap по сыгранным играм
        # строится на отдельных уведомлениях Final scores выше.
        week, games = parse_weekly_board(raw_text)
        if week == "?":
            return

        if not any(g.is_completed for g in games):
            if state.is_new(schedule_key(week)):
                schedule_text = format_schedule_message(week, games)
                sent = await bot.send_message(
                    settings.recap_chat_id, schedule_text, parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                state.mark_seen(schedule_key(week))
                save_week_games(state, week, games)

                old_pinned = state.get_meta("pinned_schedule_message_id")
                if old_pinned:
                    try:
                        await bot.unpin_chat_message(settings.recap_chat_id, message_id=int(old_pinned))
                    except TelegramBadRequest as e:
                        log.warning("Не удалось открепить прошлое расписание (%s)", e)
                try:
                    await bot.pin_chat_message(settings.recap_chat_id, sent.message_id, disable_notification=True)
                    state.set_meta("pinned_schedule_message_id", str(sent.message_id))
                except TelegramBadRequest as e:
                    log.warning("Не удалось закрепить расписание (%s) — у бота есть право 'Закреплять сообщения'?", e)
            return

        # Неделя уже в процессе (где-то есть счёт) — напоминаем, какие игры ещё не сыграны.
        # Срабатывает заново только когда сам набор оставшихся игр меняется.
        unplayed = [g for g in games if not g.is_completed]
        if unplayed:
            rkey = remaining_key(week, unplayed)
            if state.is_new(rkey):
                text = format_remaining_message(week, unplayed)
                await bot.send_message(
                    settings.recap_chat_id, text, parse_mode="HTML",
                    link_preview_options=LinkPreviewOptions(is_disabled=True),
                )
                state.mark_seen(rkey)
    return handle_recap


async def main() -> None:
    global store, llm, tools, KNOWLEDGE, BOT_USER, recap_state, recap_handler
    settings.validate()

    if settings.recap_reset_on_start and settings.recap_state_path.exists():
        settings.recap_state_path.unlink()
        log.warning(
            "RECAP_RESET_ON_START=1: сброшен %s. Не забудь выключить эту переменную после теста, "
            "иначе каждый рестарт будет заново анонсировать текущую неделю/игры.",
            settings.recap_state_path,
        )
    recap_state = RecapState(settings.recap_state_path)

    KNOWLEDGE = load_knowledge(settings.knowledge_dir)
    store = MessageStore(settings.db_path)
    llm = LLMClient(
        base_url=settings.api_base_url,
        api_key=settings.api_key,
        model=settings.model,
        fallback_model=settings.fallback_model,
        reasoning_effort=settings.reasoning_effort,
        temperature=settings.temperature,
        max_tokens=settings.max_tokens,
        timeout=settings.request_timeout,
        max_concurrent=settings.max_concurrent_requests,
        max_tool_rounds=settings.max_tool_rounds,
    )
    tools = ToolRunner(settings.tavily_api_key, settings.search_max_results)

    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=None))
    BOT_USER = await bot.get_me()
    log.info(
        "Бот @%s запущен. Модель: %s. База знаний: %s символов. Поиск: %s",
        BOT_USER.username, settings.model, len(KNOWLEDGE), "вкл" if tools.tools else "выкл",
    )

    await bot.set_my_commands([
        BotCommand(command="help", description="Как пользоваться ботом"),
        BotCommand(command="rules", description="Про регламент лиги"),
        BotCommand(command="reset", description="Сбросить диалог (в личке)"),
        BotCommand(command="id", description="Показать chat_id и user_id"),
    ])

    dp = Dispatcher()
    dp.include_router(router)
    cleanup_task = asyncio.create_task(periodic_cleanup())

    discord_client: RecapRelayClient | None = None
    discord_task: asyncio.Task | None = None
    if settings.recap_relay_enabled:
        recap_handler = make_recap_handler(bot)
        discord_client = RecapRelayClient(
            channel_id=settings.discord_recap_channel_id,
            source_bot_id=settings.discord_source_bot_id,
            on_recap=recap_handler,
        )
        discord_task = asyncio.create_task(discord_client.start(settings.discord_bot_token))
        log.info("Discord-relay включён: канал %s -> Telegram чат %s", settings.discord_recap_channel_id, settings.recap_chat_id)
    else:
        log.info("Discord-relay выключен (не заданы DISCORD_BOT_TOKEN / DISCORD_RECAP_CHANNEL_ID / RECAP_CHAT_ID)")

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        cleanup_task.cancel()
        if discord_task is not None:
            discord_task.cancel()
        if discord_client is not None:
            await discord_client.close()
        await llm.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
