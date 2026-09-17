"""Кто из владельцев согласовал время своей игры — по реплаям на пост с расписанием.

Команда определяется НЕ по тексту (люди пишут по-разному, часто по-русски), а по тому,
чей Telegram-аккаунт ответил — сверяем с teams_map.TEAMS. Если ответил не владелец
команды из этой недели, разобрать не можем (и не подгадываем).
"""
import json
from dataclasses import asdict, dataclass

from dateparser.search import search_dates

from recap_state import RecapState
from teams_map import TEAMS, tag

_DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "TIMEZONE": "Europe/Moscow",
    "RETURN_AS_TIMEZONE_AWARE": True,
}


def find_team_by_telegram(username: str | None, user_id: int | None) -> str | None:
    uname = (username or "").lstrip("@").lower()
    uid = str(user_id) if user_id is not None else None
    for abbr, t in TEAMS.items():
        handle = t["telegram"].lstrip("@")
        if handle.isdigit():
            if uid and handle == uid:
                return abbr
        elif uname and handle.lower() == uname:
            return abbr
    return None


def parse_game_time(text: str):
    """Возвращает datetime или None. Ищет дату/время ВНУТРИ произвольной фразы
    ("го завтра в 21:00, го?"), а не требует, чтобы вся строка была датой."""
    results = search_dates(text, languages=["ru"], settings=_DATEPARSER_SETTINGS)
    if not results:
        return None
    return results[0][1]


def _week_games_key(week: str) -> str:
    return f"week_games:{week}"


def _gametime_key(week: str, away: str, home: str) -> str:
    return f"gametime:{week}:{away}:{home}"


def save_week_games(state: RecapState, week: str, games) -> None:
    """games — список объектов с .away/.home (recap.GameEvent)."""
    payload = [[g.away, g.home] for g in games]
    state.set_meta("current_week", week)
    state.set_meta(_week_games_key(week), json.dumps(payload, ensure_ascii=False))


def load_week_games(state: RecapState, week: str) -> list[tuple[str, str]]:
    raw = state.get_meta(_week_games_key(week))
    if not raw:
        return []
    return [(away, home) for away, home in json.loads(raw)]


def find_game_for_team(state: RecapState, week: str, team: str) -> tuple[str, str] | None:
    for away, home in load_week_games(state, week):
        if team in (away, home):
            return away, home
    return None


@dataclass
class GameTimeRecord:
    when_display: str
    by_user: str


def save_gametime(state: RecapState, week: str, away: str, home: str, record: GameTimeRecord) -> None:
    state.set_meta(_gametime_key(week, away, home), json.dumps(asdict(record), ensure_ascii=False))


def load_gametime(state: RecapState, week: str, away: str, home: str) -> GameTimeRecord | None:
    raw = state.get_meta(_gametime_key(week, away, home))
    if not raw:
        return None
    return GameTimeRecord(**json.loads(raw))


WEEKDAYS_RU = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


def format_when(dt) -> str:
    return f"{WEEKDAYS_RU[dt.weekday()]} {dt.strftime('%d.%m %H:%M')}"


def format_status_message(state: RecapState, week: str) -> str:
    games = load_week_games(state, week)
    if not games:
        return "Пока нет данных о расписании этой недели."
    lines = [f"<b>Статус игр · Неделя {week}</b>", ""]
    for away, home in games:
        record = load_gametime(state, week, away, home)
        if record:
            lines.append(f"✅ {tag(away)} — {tag(home)}: {record.when_display}")
        else:
            lines.append(f"❗️ {tag(away)} — {tag(home)}: ещё не согласовано")
    return "\n".join(lines)
