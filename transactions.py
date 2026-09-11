"""Разбор уведомлений MTFranchiseBot о трансферах (команда `Transactions`) для админ-чата.

Формат (тот же канал Discord, что и `scores`):
    Transactions

    SIGNING: 2 · POSITION_CHANGE: 5

    SEA - SIGNING: Jack Conklin
    SEA - POSITION_CHANGE: Jack Conklin
    DET - SIGNING: Jack Kiser
    ...

    Data as of 2026-09-11T09:45:35.524Z
"""
import re
from dataclasses import dataclass

from teams_map import TEAMS, tag

_ABBR = "|".join(sorted((re.escape(a) for a in TEAMS), key=len, reverse=True))
_TX_LINE_RE = re.compile(rf"^\s*(?P<team>{_ABBR})\s*-\s*(?P<type>[A-Z_]+)\s*:\s*(?P<player>.+?)\s*$", re.IGNORECASE)

_TYPE_LABELS = {
    "SIGNING": "Подписание",
    "RELEASE": "Отчисление",
    "POSITION_CHANGE": "Смена позиции",
    "TRADE": "Трейд",
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
    for line in raw_text.splitlines():
        m = _TX_LINE_RE.match(line.strip())
        if m:
            events.append(TransactionEvent(
                team=m.group("team").upper(),
                type=m.group("type").upper(),
                player=m.group("player").strip(),
            ))
    return events


def format_transaction_line(event: TransactionEvent) -> str:
    label = _TYPE_LABELS.get(event.type, event.type.replace("_", " ").title())
    return f"{tag(event.team)} — {label}: {event.player}"


def format_transactions_message(events: list[TransactionEvent]) -> str:
    lines = ["<b>Трансферы</b>", ""]
    lines += [format_transaction_line(e) for e in events]
    return "\n".join(lines)
