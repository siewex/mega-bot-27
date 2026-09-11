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

from teams_map import TEAMS, tag

_ABBR = "|".join(sorted((re.escape(a) for a in TEAMS), key=len, reverse=True))
_COMPLETED_RE = re.compile(
    rf"^\s*(?P<away>{_ABBR})\s+(?P<away_score>\d{{1,3}})\s*[·|]\s*(?P<home>{_ABBR})\s+(?P<home_score>\d{{1,3}})\s*$",
    re.IGNORECASE,
)
_SCHEDULED_RE = re.compile(rf"^\s*(?P<away>{_ABBR})\s*@\s*(?P<home>{_ABBR})\s*$", re.IGNORECASE)
_WEEK_RE = re.compile(r"week\s*(\d+)", re.IGNORECASE)


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
            week = wm.group(1)
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


def game_key(event: GameEvent) -> str:
    return f"game:{event.week}:{event.away}:{event.home}"


def schedule_key(week: str) -> str:
    return f"schedule:{week}"


def format_schedule_message(week: str, games: list[GameEvent]) -> str:
    lines = [f"📋 <b>Расписание · Неделя {week}</b>", ""]
    for g in games:
        lines.append(f"{tag(g.away)}  —  {tag(g.home)}")
    return "\n".join(lines)


RECAP_SYSTEM_PROMPT = (
    "Ты спортивный комментатор фэнтези-лиги Madden NFL. По итоговому счёту матча пиши "
    "короткий (1 предложение) эмоциональный комментарий на русском языке. Подробной "
    "статистики игроков нет — не выдумывай её, опирайся только на счёт и разницу очков."
)


async def generate_blurb(llm, event: GameEvent) -> str:
    user_content = f"Неделя {event.week}: {event.away} {event.away_score} — {event.home_score} {event.home}."
    messages = [
        {"role": "system", "content": RECAP_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    return await llm.complete(messages)


def format_telegram_message(event: GameEvent, blurb_html: str) -> str:
    winner = event.away if event.away_score > event.home_score else event.home
    win_score, lose_score = sorted((event.away_score, event.home_score), reverse=True)
    lines = [
        f"🏈 <b>GAME RECAP · Неделя {event.week}</b>",
        "",
        f"{tag(event.away)} — {event.away_score}:{event.home_score} — {tag(event.home)}",
        f"🏆 {tag(winner)} ({win_score}-{lose_score})",
    ]
    if blurb_html.strip():
        lines += ["", blurb_html.strip()]
    return "\n".join(lines)
