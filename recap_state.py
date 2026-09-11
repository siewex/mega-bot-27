"""Какие игры уже анонсированы в Telegram — чтобы не дублировать recap при повторной сводке."""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class RecapState:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        if self.path.exists():
            try:
                self._seen = set(json.loads(self.path.read_text(encoding="utf-8")))
            except Exception:
                log.exception("Не удалось прочитать %s, начинаю с пустого состояния", self.path)

    def is_new(self, key: str) -> bool:
        return key not in self._seen

    def mark_seen(self, key: str) -> None:
        self._seen.add(key)
        self.path.write_text(json.dumps(sorted(self._seen), ensure_ascii=False, indent=2), encoding="utf-8")
