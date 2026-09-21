"""Разбор box-score уведомлений MTFranchiseBot (со статами топ-игроков по каждой команде).

Формат (пример реального сообщения):
    TB 27 @ CIN 21 · Week 1  (https://...)
    :mt_tb: TB Buccaneers 27 · teodossi · 1-0-0
    :mt_cin: CIN Bengals 21 · asttema · 0-1-0

    Box score
    :mt_tb: TB
    Baker Mayfield
    21/36, 250 yds, 2 TD
    Kenny Gainwell
    13 carries, 60 yds
    Ted Hurst III
    6 rec, 136 yds, 1 TD
    Vita Vea
    3 tkl, 1.5 sacks
    :mt_cin: CIN
    ... (те же 4 категории)

По каждой команде всегда 4 пары (игрок, стата) — пас/ран/приём/защита, но категорию
на всякий случай определяем по содержимому строки статы, а не по порядку.
"""
import re
from dataclasses import dataclass, field

from teams_map import TEAMS, tag

_ABBR = "|".join(sorted((re.escape(a) for a in TEAMS), key=len, reverse=True))

_HEADER_RE = re.compile(
    rf"(?P<away>{_ABBR})\s+(?P<away_score>\d{{1,3}})\s*@\s*(?P<home>{_ABBR})\s+(?P<home_score>\d{{1,3}})"
    rf"\s*·\s*Week\s*(?P<week>\d+)",
    re.IGNORECASE,
)

CATEGORY_LABELS = {"pass": "🎯 Пас", "rush": "🏃 Ран", "rec": "🙌 Приём", "def": "🛡 Защита"}


@dataclass
class PlayerStat:
    category: str  # "pass" | "rush" | "rec" | "def"
    name: str
    line: str


@dataclass
class BoxScore:
    week: str
    away: str
    home: str
    away_score: int
    home_score: int
    away_stats: list[PlayerStat] = field(default_factory=list)
    home_stats: list[PlayerStat] = field(default_factory=list)


def is_boxscore_message(raw_text: str) -> bool:
    return "box score" in raw_text.lower()


def boxscore_key(box: BoxScore) -> str:
    return f"boxscore:{box.week}:{box.away}:{box.away_score}:{box.home}:{box.home_score}"


def _guess_category(stat_line: str) -> str:
    low = stat_line.lower()
    if "carries" in low:
        return "rush"
    if "rec" in low or "receiv" in low:
        return "rec"
    if "/" in stat_line and ("yds" in low or "td" in low or "int" in low):
        return "pass"
    return "def"


def _strip_leading_emoji(line: str) -> str:
    # Discord-эмодзи в сыром тексте могут выглядеть и как <:name:id> (обычно уже вырезано
    # discord_relay._CUSTOM_EMOJI_RE до нас), и как текстовый шорткод :name: (если скопировано
    # вручную из клиента) — чистим оба варианта, плюс любой прочий небуквенный мусор спереди.
    line = re.sub(r"^:[\w]+:\s*", "", line)
    line = re.sub(r"^[^\wА-Яа-я]+", "", line)
    return line.strip()


# Копипаст из Discord иногда теряет переносы строк внутри блока статы, и все 4 игрока
# команды слипаются в одну строку без разделителей ("Baker Mayfield 21/36, 250 yds, 2 TD
# Kenny Gainwell 13 carries, 60 yds ..."). Поэтому вместо жёсткой пары "строка-имя +
# строка-стата" достаём все пары (игрок, стата) из блока целиком одним паттерном —
# работает и когда строки разделены переносами, и когда слиплись в одну.
_PLAYER_STAT_RE = re.compile(
    r"(?P<name>[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,3}?)\s+"
    r"(?P<stat>\d[^A-Z]*(?:[A-Z]{1,3}(?![a-z])[^A-Z]*)*)"
)


def _extract_player_stats(block: str) -> list[PlayerStat]:
    # MTFranchiseBot иногда оборачивает имена в markdown **bold** — звёздочки разрывают
    # связку "имя -> пробел -> цифра статы" в регэкспе, поэтому просто убираем их.
    joined = " ".join(ln.strip() for ln in block.splitlines() if ln.strip()).replace("*", "")
    return [
        PlayerStat(category=_guess_category(m.group("stat")), name=m.group("name").strip(), line=m.group("stat").strip())
        for m in _PLAYER_STAT_RE.finditer(joined)
    ]


def _parse_one_boxscore(header: re.Match, segment: str) -> BoxScore:
    """segment — текст СТРОГО между этим заголовком и следующим (или концом сообщения),
    чтобы при нескольких играх в одном уведомлении статы одной не утекали в другую."""
    away, home = header.group("away").upper(), header.group("home").upper()
    box = BoxScore(
        week=header.group("week"), away=away, home=home,
        away_score=int(header.group("away_score")), home_score=int(header.group("home_score")),
    )

    idx = segment.lower().find("box score")
    if idx == -1:
        return box
    tail = segment[idx + len("box score"):]
    lines = [ln.strip() for ln in tail.splitlines() if ln.strip()]

    away_idx = home_idx = None
    for i, line in enumerate(lines):
        cleaned = _strip_leading_emoji(line).upper()
        if away_idx is None and cleaned == away:
            away_idx = i
        elif home_idx is None and cleaned == home:
            home_idx = i

    if away_idx is not None:
        end = home_idx if home_idx is not None and home_idx > away_idx else len(lines)
        box.away_stats = _extract_player_stats("\n".join(lines[away_idx + 1 : end]))
    if home_idx is not None:
        box.home_stats = _extract_player_stats("\n".join(lines[home_idx + 1 :]))

    return box


def parse_boxscore_messages(raw_text: str) -> list[BoxScore]:
    """MTFranchiseBot иногда пакует несколько игр в одно уведомление (как раньше было
    с Final scores) — находим ВСЕ заголовки и режем текст на непересекающиеся куски по
    ним, чтобы статы одной игры не утекали в соседнюю."""
    headers = list(_HEADER_RE.finditer(raw_text))
    boxes = []
    for i, header in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(raw_text)
        segment = raw_text[header.end() : end]
        boxes.append(_parse_one_boxscore(header, segment))
    return boxes


def parse_boxscore(raw_text: str) -> BoxScore | None:
    """Обратная совместимость: только первая игра из уведомления. Для пачки игр
    используй parse_boxscore_messages."""
    boxes = parse_boxscore_messages(raw_text)
    return boxes[0] if boxes else None


BOXSCORE_SYSTEM_PROMPT = (
    "Ты спортивный комментатор фэнтези-лиги Madden NFL. По статистике матча пиши "
    "короткий (1-2 предложения) эмоциональный recap на русском языке, упоминая конкретных "
    "игроков и их реальные цифры из статистики. Никогда не выдумывай цифры и события, "
    "которых нет в переданных данных."
)


def _stats_text(stats: list[PlayerStat]) -> str:
    return "\n".join(f"{s.name}: {s.line}" for s in stats) or "(нет данных)"


async def generate_boxscore_blurb(llm, box: BoxScore) -> str:
    user_content = (
        f"Неделя {box.week}: {box.away} {box.away_score} — {box.home_score} {box.home}.\n\n"
        f"{box.away}:\n{_stats_text(box.away_stats)}\n\n"
        f"{box.home}:\n{_stats_text(box.home_stats)}"
    )
    messages = [
        {"role": "system", "content": BOXSCORE_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    return await llm.complete(messages)


def _format_team_stats(stats: list[PlayerStat]) -> list[str]:
    return [f"{CATEGORY_LABELS.get(s.category, '')}: {s.name} — {s.line}" for s in stats]


def format_boxscore_message(box: BoxScore, blurb_html: str, include_stats: bool = True) -> str:
    """include_stats=False — для подписи к фото: статы и так видны на самой картинке,
    а у подписи к фото в Telegram лимит 1024 символа (текстовое сообщение — 4096)."""
    winner = box.away if box.away_score > box.home_score else box.home
    win_score, lose_score = sorted((box.away_score, box.home_score), reverse=True)
    lines = [
        f"<b>GAME RECAP · Неделя {box.week}</b>",
        "",
        f"{tag(box.away)} — {box.away_score}:{box.home_score} — {tag(box.home)}",
        f"Победа: {tag(winner)} ({win_score}-{lose_score})",
    ]
    if blurb_html.strip():
        lines += ["", blurb_html.strip()]
    if include_stats and (box.away_stats or box.home_stats):
        lines += ["", f"<b>{box.away}</b>", *_format_team_stats(box.away_stats)]
        lines += ["", f"<b>{box.home}</b>", *_format_team_stats(box.home_stats)]
    return "\n".join(lines)
