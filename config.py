"""Настройки бота. Всё берётся из переменных окружения (или файла .env рядом с main.py)."""
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent / ".env")
except ImportError:  # dotenv не обязателен, если переменные заданы в панели хостинга
    pass


def _str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _int(name: str, default: int) -> int:
    raw = _str(name)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _float_or_none(name: str, default: float | None) -> float | None:
    raw = _str(name)
    if raw == "":
        return default
    if raw.lower() in {"none", "off", "no", "-"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return default


def _list(name: str) -> list[str]:
    return [x.strip() for x in _str(name).replace(";", ",").split(",") if x.strip()]


def _normalize_base_url(url: str) -> str:
    url = url.strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


BASE_DIR = Path(__file__).parent


@dataclass
class Settings:
    # Telegram
    bot_token: str = field(default_factory=lambda: _str("BOT_TOKEN") or _str("TELEGRAM_BOT_TOKEN"))
    bot_name: str = field(default_factory=lambda: _str("BOT_NAME", "MEGA-бот"))
    admin_ids: set[int] = field(
        default_factory=lambda: {int(x) for x in _list("ADMIN_IDS") if x.lstrip("-").isdigit()}
    )
    commissioners: str = field(default_factory=lambda: _str("COMMISSIONERS"))
    # Слова, на которые бот откликается без тега (нужно выключить privacy mode у бота в BotFather)
    trigger_words: list[str] = field(default_factory=lambda: [w.lower() for w in _list("TRIGGER_WORDS")])
    # Если указаны — бот работает только в этих чатах (плюс личка админов)
    allowed_chat_ids: set[int] = field(
        default_factory=lambda: {int(x) for x in _list("ALLOWED_CHAT_IDS") if x.lstrip("-").isdigit()}
    )
    allow_private: bool = field(default_factory=lambda: _str("ALLOW_PRIVATE", "1") not in {"0", "false", "no"})

    # LLM (OpenAI-совместимый API)
    api_base_url: str = field(
        default_factory=lambda: _normalize_base_url(_str("API_BASE_URL", "https://shprotoness-ai.jq9gfk.workers.dev/v1"))
    )
    api_key: str = field(default_factory=lambda: _str("API_KEY"))
    model: str = field(default_factory=lambda: _str("MODEL", "grok-4.5"))
    fallback_model: str = field(default_factory=lambda: _str("FALLBACK_MODEL", "deepseek-v4-flash"))
    reasoning_effort: str = field(default_factory=lambda: _str("REASONING_EFFORT", "low"))
    temperature: float | None = field(default_factory=lambda: _float_or_none("TEMPERATURE", 0.8))
    max_tokens: int = field(default_factory=lambda: _int("MAX_TOKENS", 1500))
    request_timeout: int = field(default_factory=lambda: _int("REQUEST_TIMEOUT", 90))

    # Поиск в интернете (Tavily). Пустой ключ = поиск выключен
    tavily_api_key: str = field(default_factory=lambda: _str("TAVILY_API_KEY"))
    search_max_results: int = field(default_factory=lambda: _int("SEARCH_MAX_RESULTS", 5))
    max_tool_rounds: int = field(default_factory=lambda: _int("MAX_SEARCHES_PER_ANSWER", 2))

    # Диалог и лимиты
    history_limit: int = field(default_factory=lambda: _int("HISTORY_LIMIT", 14))
    cooldown_seconds: int = field(default_factory=lambda: _int("COOLDOWN_SECONDS", 5))
    daily_limit_per_user: int = field(default_factory=lambda: _int("DAILY_LIMIT", 40))
    max_concurrent_requests: int = field(default_factory=lambda: _int("MAX_CONCURRENT", 4))
    max_question_chars: int = field(default_factory=lambda: _int("MAX_QUESTION_CHARS", 3000))
    history_ttl_days: int = field(default_factory=lambda: _int("HISTORY_TTL_DAYS", 14))

    # Файлы. DATA_DIR — конвенция хостинга (Bothost): папка, которая переживает перезапуск контейнера.
    data_dir: Path = field(default_factory=lambda: Path(_str("DATA_DIR") or BASE_DIR / "data"))
    knowledge_dir: Path = field(default_factory=lambda: Path(_str("KNOWLEDGE_DIR") or BASE_DIR / "knowledge"))
    db_path: Path | None = field(default_factory=lambda: Path(_str("DB_PATH")) if _str("DB_PATH") else None)

    # Recap-relay: Discord (MTFranchiseBot) -> LLM -> Telegram
    discord_bot_token: str = field(default_factory=lambda: _str("DISCORD_BOT_TOKEN"))
    discord_recap_channel_id: int = field(default_factory=lambda: _int("DISCORD_RECAP_CHANNEL_ID", 0))
    discord_source_bot_id: int | None = field(
        default_factory=lambda: (int(_str("DISCORD_SOURCE_BOT_ID")) if _str("DISCORD_SOURCE_BOT_ID") else None)
    )
    recap_chat_id: int = field(default_factory=lambda: _int("RECAP_CHAT_ID", 0))
    transactions_chat_id: int = field(default_factory=lambda: _int("TRANSACTIONS_CHAT_ID", 0))
    recap_state_path: Path | None = field(
        default_factory=lambda: Path(_str("RECAP_STATE_PATH")) if _str("RECAP_STATE_PATH") else None
    )
    # На один рестарт: сбросить recap_state.json (заново анонсировать текущую неделю/игры), затем выключить.
    recap_reset_on_start: bool = field(
        default_factory=lambda: _str("RECAP_RESET_ON_START") in {"1", "true", "yes"}
    )

    def __post_init__(self) -> None:
        if self.db_path is None:
            self.db_path = self.data_dir / "bot.sqlite3"
        if self.recap_state_path is None:
            self.recap_state_path = self.data_dir / "recap_state.json"

    @property
    def recap_relay_enabled(self) -> bool:
        return bool(self.discord_bot_token and self.discord_recap_channel_id and self.recap_chat_id)

    def validate(self) -> None:
        missing = [n for n, v in (("BOT_TOKEN", self.bot_token), ("API_KEY", self.api_key)) if not v]
        if missing:
            raise SystemExit(f"Не заданы обязательные переменные окружения: {', '.join(missing)}")
        if not self.knowledge_dir.is_dir():
            raise SystemExit(f"Не найдена папка с базой знаний: {self.knowledge_dir}")


settings = Settings()
