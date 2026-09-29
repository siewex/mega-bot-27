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

    def claim(self, key: str) -> bool:
        """Проверить и сразу занять ключ. Занимать нужно ДО любых await: одно и то же
        сообщение Discord может прийти дважды подряд (MESSAGE_CREATE и MESSAGE_UPDATE,
        когда Discord дорисовывает превью ссылки), и второй обработчик иначе успеет
        пройти проверку, пока первый ждёт LLM."""
        if key in self._seen:
            return False
        self.mark_seen(key)
        return True

    def forget(self, key: str) -> None:
        """Откатить claim, если отправить не получилось — чтобы следующая попытка прошла."""
        if key in self._seen:
            self._seen.discard(key)
            self._save()

    def get_meta(self, key: str) -> str | None:
        return self._meta.get(key)

    def set_meta(self, key: str, value: str) -> None:
        self._meta[key] = value
        self._save()

    def _save(self) -> None:
        data = {"seen": sorted(self._seen), "meta": self._meta}
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
