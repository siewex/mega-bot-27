"""Кто из владельцев согласовал время своей игры — по реплаям на пост с расписанием.

Команда определяется НЕ по тексту (люди пишут по-разному, часто по-русски), а по тому,
чей Telegram-аккаунт ответил — сверяем с teams_map.TEAMS. Если ответил не владелец
команды из этой недели, разобрать не можем (и не подгадываем).

Исключение — "форс" (декларация форсированного результата из-за неявки соперника):
тут команду, наоборот, нужно достать из текста (форсит обычно соперник, а не сам
форсируемый), поэтому для этого конкретного случая есть словарь русских названий команд.
"""
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from dateparser.search import search_dates

from recap_state import RecapState
from teams_map import TEAMS, tag

MSK = timezone(timedelta(hours=3))

_DATEPARSER_SETTINGS = {
    "PREFER_DATES_FROM": "future",
    "TIMEZONE": "Europe/Moscow",
    "RETURN_AS_TIMEZONE_AWARE": True,
}

# "23.09 9.30" / "23.09.2026 21:00" / "23.09" — распространённый формат, с которым
# dateparser.search_dates справляется плохо (путает день/месяц с частями времени).
_NUMERIC_DATE_RE = re.compile(
    r"(?<!\d)(?P<day>\d{1,2})\.(?P<month>\d{1,2})(?:\.(?P<year>\d{2,4}))?"
    r"(?:\s+(?:в\s+)?(?P<hour>\d{1,2})[.:](?P<minute>\d{2}))?"
)

TEAM_ALIASES_RU: dict[str, list[str]] = {
    "PIT": ["питтсбург", "стилерс"],
    "CIN": ["цинциннати", "бенгалс", "бенгалы"],
    "CLE": ["кливленд", "браунс"],
    "BAL": ["балтимор", "рэйвенс", "рейвенс", "вороны"],
    "NE": ["нью-ингленд", "патриотс", "патриоты"],
    "MIA": ["майами", "долфинс", "дельфины"],
    "BUF": ["буффало", "биллс"],
    "NYJ": ["джетс"],
    "TEN": ["теннесси", "тайтенс", "титанс"],
    "IND": ["индианаполис", "колтс"],
    "HOU": ["хьюстон", "тексанс"],
    "JAX": ["джексонвилл", "джагуарс", "ягуары"],
    "LV": ["лас-вегас", "рейдерс", "рэйдерс"],
    "DEN": ["денвер", "бронкос"],
    "LAC": ["чарджерс", "чарджеры"],
    "KC": ["канзас-сити", "канзас", "чифс"],
    "MIN": ["миннесота", "вайкингс", "викинги"],
    "DET": ["детройт", "лайонс", "львы"],
    "CHI": ["чикаго", "беарс", "медведи"],
    "GB": ["грин-бей", "пэкерс", "пакерс"],
    "PHI": ["филадельфия", "иглз", "орлы"],
    "NYG": ["джайентс", "гиганты"],
    "WAS": ["вашингтон", "командерс"],
    "DAL": ["даллас", "ковбойс", "ковбои"],
    "ATL": ["атланта", "фэлконс", "фалконс", "соколы"],
    "TB": ["тампа", "бакканирс", "буканьеры"],
    "CAR": ["каролина", "пантерс", "пантеры"],
    "NO": ["нью-орлеан", "сэйнтс", "сейнтс", "святые"],
    "SEA": ["сиэтл", "сихокс"],
    "SF": ["сан-франциско", "найнерс"],
    "LAR": ["рэмс", "рэймс", "рамс"],
    "AZ": ["аризона", "кардиналс"],
    "ARI": ["аризона", "кардиналс"],
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


def find_team_by_name(text: str) -> str | None:
    """Ищет команду по русскому названию/абревиатуре В ТЕКСТЕ (для "форса" — там
    команду называет соперник, а не сам владелец, так что по identity не определить)."""
    low = text.lower()
    aliases = sorted(
        ((alias, abbr) for abbr, names in TEAM_ALIASES_RU.items() for alias in names),
        key=lambda pair: len(pair[0]), reverse=True,
    )
    for alias, abbr in aliases:
        if alias in low:
            return abbr
    for abbr in sorted(TEAMS, key=len, reverse=True):
        if re.search(rf"(?<![a-zа-я0-9]){re.escape(abbr.lower())}(?![a-zа-я0-9])", low):
            return abbr
    return None


def detect_force(text: str) -> str | None:
    """Если в реплае есть слово "форс" — возвращает аббревиатуру упомянутой там команды."""
    if "форс" not in text.lower():
        return None
    return find_team_by_name(text)


def _parse_numeric_datetime(text: str):
    m = _NUMERIC_DATE_RE.search(text)
    if not m:
        return None
    day, month = int(m.group("day")), int(m.group("month"))
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    now = datetime.now(MSK)
    year_raw = m.group("year")
    year = now.year if not year_raw else (2000 + int(year_raw) if len(year_raw) == 2 else int(year_raw))
    hour = int(m.group("hour")) if m.group("hour") else 0
    minute = int(m.group("minute")) if m.group("minute") else 0
    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=MSK)
    except ValueError:
        return None
    if year_raw is None and dt < now - timedelta(hours=12):
        dt = dt.replace(year=year + 1)
    return dt


def parse_game_time(text: str):
    """Возвращает datetime или None. Сначала пробует точный числовой формат
    ("23.09 21:00" / "23.09.2026 9.30" — с ним dateparser путается), затем
    свободный русский текст ("го завтра в 21:00")."""
    dt = _parse_numeric_datetime(text)
    if dt:
        return dt
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
    forced_against: str | None = None


def save_gametime(state: RecapState, week: str, away: str, home: str, record: GameTimeRecord) -> None:
    """Перезаписывает предыдущую запись для этой игры целиком (последний реплай побеждает)."""
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
        if record and record.forced_against:
            lines.append(f"⚠️ {tag(away)} — {tag(home)}: форс против {tag(record.forced_against)}")
        elif record:
            lines.append(f"✅ {tag(away)} — {tag(home)}: {record.when_display}")
        else:
            lines.append(f"❗️ {tag(away)} — {tag(home)}: ещё не согласовано")
    return "\n".join(lines)
