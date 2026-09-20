"""Разбор уведомлений MTFranchiseBot о трансферах (команда `Transactions`) для админ-чата.

Формат менялся минимум дважды. Старый (однострочный):
    Transactions

    SIGNING: 2 · POSITION_CHANGE: 5

    SEA - SIGNING: Jack Conklin
    DET - SIGNING: Jack Kiser

Новый (заголовок категории на отдельной строке, без типа в самой записи):
    Transactions

    Signings · 1
    TB · Dameon Pierce

    Team changes · 1
    KC · Daniel Faalele

    Data as of ...

Поддерживаем оба варианта — на случай что формат снова сменят/откатят.
"""
import re
from dataclasses import dataclass

from teams_map import TEAMS, tag

_ABBR = "|".join(sorted((re.escape(a) for a in TEAMS), key=len, reverse=True))

# Старый формат: "SEA - SIGNING: Jack Conklin" / "JAX · SIGNING: DaQuan Jones"
_OLD_LINE_RE = re.compile(rf"^\s*(?P<team>{_ABBR})\s*[-·]\s*(?P<type>[A-Z_]+)\s*:\s*(?P<player>.+?)\s*$", re.IGNORECASE)

# Новый формат: заголовок категории "Signings · 1" / "Team changes · 2", затем N строк
# "TB · Dameon Pierce" (без типа в самой строке — тип берём из последнего заголовка).
_SECTION_HEADER_RE = re.compile(r"^[A-Za-zА-Яа-я][A-Za-zА-Яа-я ]*\s*·\s*\d+\s*$")
_NEW_ENTRY_RE = re.compile(rf"^\s*(?P<team>{_ABBR})\s*·\s*(?P<player>.+?)\s*$", re.IGNORECASE)

_TYPE_LABELS = {
    "SIGNING": "Подписание", "SIGNINGS": "Подписание",
    "RELEASE": "Отчисление", "RELEASES": "Отчисление",
    "POSITION_CHANGE": "Смена позиции", "TEAM CHANGES": "Изменение состава",
    "TRADE": "Трейд", "TRADES": "Трейд",
    "IR": "Список травмированных",
    "PRACTICE_SQUAD": "Практис-сквад",
}


@dataclass
class TransactionEvent:
    team: str
    type: str
    player: str

    def key(self) -> str:
        return f"tx:{self.team}:{self.type}:{self.player}"


def is_transactions_message(raw_text: str) -> bool:
    return raw_text.strip().lower().startswith("transactions")


def parse_transactions(raw_text: str) -> list[TransactionEvent]:
    events: list[TransactionEvent] = []
    current_label: str | None = None

    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("data as of") or line.lower() == "transactions":
            continue

        old_m = _OLD_LINE_RE.match(line)
        if old_m:
            events.append(TransactionEvent(
                team=old_m.group("team").upper(),
                type=old_m.group("type").upper(),
                player=old_m.group("player").strip(),
            ))
            continue

        if _SECTION_HEADER_RE.match(line):
            current_label = line.rsplit("·", 1)[0].strip()
            continue

        new_m = _NEW_ENTRY_RE.match(line)
        if new_m and current_label:
            events.append(TransactionEvent(
                team=new_m.group("team").upper(),
                type=current_label,
                player=new_m.group("player").strip(),
            ))

    return events


def format_transaction_line(event: TransactionEvent) -> str:
    label = _TYPE_LABELS.get(event.type.upper(), event.type)
    return f"{tag(event.team)} — {label}: {event.player}"


def format_transactions_message(events: list[TransactionEvent]) -> str:
    lines = ["<b>Трансферы</b>", ""]
    lines += [format_transaction_line(e) for e in events]
    return "\n".join(lines)
