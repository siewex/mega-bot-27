"""Разбор вывода MTFranchiseBot (команда `scores`) и сборка сообщений для Telegram:
расписание недели (один раз при переходе на новую неделю) и recap по сыгранным играм.

Бот присылает сводку по всей неделе разом, например:
    Scores: Week 1
    DET @ CIN          <- ещё не сыграна (это же и есть расписание)
    MIN 17 · NYG 38    <- сыграна, есть счёт
    ...
Детальной статистики игроков сейчас нет (разработчик обещал добавить позже) —
recap строится только на финальном счёте. Одна и та же сводка может прилетать
повторно (каждый экспорт), поэтому что уже анонсировано (расписание такой-то
недели, recap такой-то игры) — отслеживает recap_state.RecapState.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from teams_map import TEAMS, tag

MSK = timezone(timedelta(hours=3))
SCHEDULE_DEADLINE_HOURS = 40

_ABBR = "|".join(sorted((re.escape(a) for a in TEAMS), key=len, reverse=True))
_COMPLETED_RE = re.compile(
    rf"^\s*(?P<away>{_ABBR})\s+(?P<away_score>\d{{1,3}})\s*[·|]\s*(?P<home>{_ABBR})\s+(?P<home_score>\d{{1,3}})\s*$",
    re.IGNORECASE,
)
_SCHEDULED_RE = re.compile(rf"^\s*(?P<away>{_ABBR})\s*@\s*(?P<home>{_ABBR})\s*$", re.IGNORECASE)
# "Preseason Week 1" и просто "Week 1" — разные недели, у них не должен совпадать ключ дедупа.
_WEEK_RE = re.compile(r"(pre[\s-]?season\s+)?week\s*(\d+)", re.IGNORECASE)

# Отдельное авто-уведомление MTFranchiseBot по каждой сыгранной игре, например:
#   Final scores
#   SF 0 @ LAC 31
#   Data as of ...
# В отличие от сводки `scores`, номера недели тут нет.
_FINAL_SCORE_RE = re.compile(
    rf"(?P<away>{_ABBR})\s+(?P<away_score>\d{{1,3}})\s*@\s*(?P<home>{_ABBR})\s+(?P<home_score>\d{{1,3}})",
    re.IGNORECASE,
)


@dataclass
class GameEvent:
    week: str
    away: str
    home: str
    away_score: int | None
    home_score: int | None

    @property
    def is_completed(self) -> bool:
        return self.away_score is not None and self.home_score is not None


def parse_weekly_board(raw_text: str) -> tuple[str, list[GameEvent]]:
    """Возвращает номер недели и все матчи из сводки (и сыгранные, и ещё нет)."""
    lines = raw_text.splitlines()
    week = "?"
    for line in lines:
        wm = _WEEK_RE.search(line)
        if wm:
            week = f"pre-{wm.group(2)}" if wm.group(1) else wm.group(2)
            break

    games: list[GameEvent] = []
    for raw_line in lines:
        line = raw_line.strip()
        m = _COMPLETED_RE.match(line)
        if m:
            games.append(GameEvent(
                week, m.group("away").upper(), m.group("home").upper(),
                int(m.group("away_score")), int(m.group("home_score")),
            ))
            continue
        m = _SCHEDULED_RE.match(line)
        if m:
            games.append(GameEvent(week, m.group("away").upper(), m.group("home").upper(), None, None))
    return week, games


def is_final_score_message(raw_text: str) -> bool:
    return "final score" in raw_text.strip().lower()


def parse_final_score_message(raw_text: str) -> GameEvent | None:
    m = _FINAL_SCORE_RE.search(raw_text)
    if not m:
        return None
    return GameEvent(
        week="",
        away=m.group("away").upper(),
        home=m.group("home").upper(),
        away_score=int(m.group("away_score")),
        home_score=int(m.group("home_score")),
    )


def game_key(event: GameEvent) -> str:
    if event.week and event.week != "?":
        return f"game:{event.week}:{event.away}:{event.home}"
    # Уведомление Final scores не содержит номер недели — дедуп по самому счёту.
    return f"game:{event.away}:{event.away_score}:{event.home}:{event.home_score}"


def schedule_key(week: str) -> str:
    return f"schedule:{week}"


REGLAMENT_URL = "https://docs.google.com/document/d/1cHbgmnUaXN4A5dCJxLxayCvIlJ6pMBMUxN8HlX1vxPs/edit?usp=drivesdk"
MADDEN_TOOLS_URL = "https://madden.tools/franchise/leagues/00a9f6ec-c3f8-4c0b-b45b-c133075be445"


def format_schedule_message(week: str, games: list[GameEvent]) -> str:
    lines = [f"<b>Расписание · Неделя {week}</b>", ""]
    for g in games:
        lines.append(f"{tag(g.away)} — {tag(g.home)}")

    deadline = datetime.now(MSK) + timedelta(hours=SCHEDULE_DEADLINE_HOURS)
    lines += [
        "",
        "❗️Пожалуйста, договоритесь прямо сейчас о матче во избежание затяжек шага.",
        "",
        f"До {deadline.strftime('%d.%m.%Y %H:%M')} (МСК) просьба указать анонс матча реплаем к этому посту.",
        "",
        f'📜 <a href="{REGLAMENT_URL}">Регламент</a>',
        f'📊 <a href="{MADDEN_TOOLS_URL}">Стата на MaddenTools</a>',
    ]
    return "\n".join(lines)


def remaining_key(week: str, unplayed: list[GameEvent]) -> str:
    matchups = sorted(f"{g.away}-{g.home}" for g in unplayed)
    return f"remaining:{week}:{','.join(matchups)}"


def format_remaining_message(week: str, unplayed: list[GameEvent]) -> str:
    lines = [f"<b>Ещё не сыграно · Неделя {week}</b>", ""]
    for g in unplayed:
        lines.append(f"{tag(g.away)} — {tag(g.home)}")
    return "\n".join(lines)


RECAP_SYSTEM_PROMPT = (
    "Ты спортивный комментатор фэнтези-лиги Madden NFL. По итоговому счёту матча пиши "
    "короткий (1 предложение) эмоциональный комментарий на русском языке. Подробной "
    "статистики игроков нет — не выдумывай её, опирайся только на счёт и разницу очков."
)


def _has_week(event: GameEvent) -> bool:
    return bool(event.week) and event.week != "?"


async def generate_blurb(llm, event: GameEvent) -> str:
    week_part = f"Неделя {event.week}: " if _has_week(event) else ""
    user_content = f"{week_part}{event.away} {event.away_score} — {event.home_score} {event.home}."
    messages = [
        {"role": "system", "content": RECAP_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    return await llm.complete(messages)


def format_telegram_message(event: GameEvent, blurb_html: str) -> str:
    winner = event.away if event.away_score > event.home_score else event.home
    win_score, lose_score = sorted((event.away_score, event.home_score), reverse=True)
    header = f"<b>GAME RECAP · Неделя {event.week}</b>" if _has_week(event) else "<b>GAME RECAP</b>"
    lines = [
        header,
        "",
        f"{tag(event.away)} — {event.away_score}:{event.home_score} — {tag(event.home)}",
        f"Победа: {tag(winner)} ({win_score}-{lose_score})",
    ]
    if blurb_html.strip():
        lines += ["", blurb_html.strip()]
    return "\n".join(lines)
