"""Что уже анонсировано в Telegram (чтобы не дублировать) + мелкие произвольные значения
(например, id закреплённого сообщения с расписанием)."""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class RecapState:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        self._meta: dict[str, str] = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, list):  # старый формат файла — просто список ключей
                    self._seen = set(data)
                elif isinstance(data, dict):
                    self._seen = set(data.get("seen") or [])
                    self._meta = dict(data.get("meta") or {})
            except Exception:
                log.exception("Не удалось прочитать %s, начинаю с пустого состояния", self.path)

    def is_new(self, key: str) -> bool:
        return key not in self._seen

    def mark_seen(self, key: str) -> None:
        self._seen.add(key)
        self._save()

    def get_meta(self, key: str) -> str | None:
        return self._meta.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self._meta[key] = value
        self._save()

    def _save(self) -> None:
        data = {"seen": sorted(self._seen), "meta": self._meta}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
