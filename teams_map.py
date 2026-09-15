"""Команды лиги: эмодзи + телеграм-аккаунт менеджера. Ключи — аббревиатуры madden.tools/MTFranchiseBot.

custom_emoji_id — премиум-эмодзи Telegram с логотипом команды (нужен Premium у владельца
бота @maddensupportbot, см. https://habr.com/ru/articles/994622/). custom_emoji_fallback —
обычный эмодзи, который увидят клиенты без поддержки кастомных эмодзи.
"""

TEAMS = {
    "PIT": {"emoji": "👷‍♂️", "telegram": "@kislik34", "custom_emoji_id": "5208532356259916321", "custom_emoji_fallback": "✨"},
    "CIN": {"emoji": "🐅", "telegram": "@Asttema", "custom_emoji_id": "5206571222652954279", "custom_emoji_fallback": "🐅"},
    "CLE": {"emoji": "🤎", "telegram": "@lespaul88", "custom_emoji_id": "5208488002132649123", "custom_emoji_fallback": "🤎"},
    "BAL": {"emoji": "🦉", "telegram": "@Arturetti", "custom_emoji_id": "5208649879450035589", "custom_emoji_fallback": "🐣"},

    "NE": {"emoji": "💂", "telegram": "@fnolzoar", "custom_emoji_id": "5208620025132362487", "custom_emoji_fallback": "🏴󠁧󠁢󠁥󠁮󠁧󠁿"},
    "MIA": {"emoji": "🐬", "telegram": "@l3dn1q", "custom_emoji_id": "5206303933953224077", "custom_emoji_fallback": "🐬"},
    "BUF": {"emoji": "🐂", "telegram": "@DaniVRN", "custom_emoji_id": "5208665603325310207", "custom_emoji_fallback": "🐂"},
    "NYJ": {"emoji": "✈️", "telegram": "@Ajoudojuau", "custom_emoji_id": "5208678982148436084", "custom_emoji_fallback": "🛩"},

    "TEN": {"emoji": "⚔️", "telegram": "@kkkkkk13_13", "custom_emoji_id": "5206388746672415857", "custom_emoji_fallback": "🔥"},
    "IND": {"emoji": "🧲", "telegram": "@GilTimRus", "custom_emoji_id": "5206314014241466902", "custom_emoji_fallback": "🐴"},
    "HOU": {"emoji": "🇨🇱", "telegram": "705595647", "custom_emoji_id": "5206189670643280699", "custom_emoji_fallback": "🏇"},
    "JAX": {"emoji": "😾", "telegram": "@StasVII", "custom_emoji_id": "5208468614650275488", "custom_emoji_fallback": "🐈"},

    "LV": {"emoji": "☠️", "telegram": "@Hvosssteg", "custom_emoji_id": "5208752254290503931", "custom_emoji_fallback": "🏴‍☠️"},
    "DEN": {"emoji": "🐎", "telegram": "@DrobiazgoD", "custom_emoji_id": "5208581374721666314", "custom_emoji_fallback": "🐴"},
    "LAC": {"emoji": "⚡️", "telegram": "@dail87", "custom_emoji_id": "5206434058577389431", "custom_emoji_fallback": "⚡️"},
    "KC": {"emoji": "🏹", "telegram": "@mahomes15", "custom_emoji_id": "5206458754639341995", "custom_emoji_fallback": "👨‍🍳"},

    "MIN": {"emoji": "🇦🇽", "telegram": "@MarcusHoper", "custom_emoji_id": "5206535630258972738", "custom_emoji_fallback": "🧭"},
    "DET": {"emoji": "🦁", "telegram": "@mishgek", "custom_emoji_id": "5206586216383785091", "custom_emoji_fallback": "🦁"},
    "CHI": {"emoji": "🐻", "telegram": "@MikeRyabikin", "custom_emoji_id": "5206672098549836409", "custom_emoji_fallback": "🐻"},
    "GB": {"emoji": "📦", "telegram": "@harley47", "custom_emoji_id": "5208574640212945194", "custom_emoji_fallback": "🟩"},

    "PHI": {"emoji": "🦅", "telegram": "@bernikoww", "custom_emoji_id": "5206328011539884358", "custom_emoji_fallback": "🦅"},
    "NYG": {"emoji": "🏙", "telegram": "@defisparta", "custom_emoji_id": "5208648389096384740", "custom_emoji_fallback": "🗽"},
    "WAS": {"emoji": "🫡", "telegram": "@Laruzz", "custom_emoji_id": "5208897394120337040", "custom_emoji_fallback": "😶"},
    "DAL": {"emoji": "🤠", "telegram": "@Chippolllino", "custom_emoji_id": "5208937414625601188", "custom_emoji_fallback": "🤠"},

    "ATL": {"emoji": "🪶", "telegram": "@Oleg_Oleynikov", "custom_emoji_id": "5206341686715754659", "custom_emoji_fallback": "🦅"},
    "TB": {"emoji": "🏴‍☠️", "telegram": "@teodossi", "custom_emoji_id": "5208947572223256404", "custom_emoji_fallback": "🏴‍☠️"},
    "CAR": {"emoji": "🐈‍⬛️", "telegram": "@udzhinable", "custom_emoji_id": "5208836903800940525", "custom_emoji_fallback": "🐈‍⬛"},
    "NO": {"emoji": "⚜️", "telegram": "@ellwoood", "custom_emoji_id": "5208779540217736904", "custom_emoji_fallback": "😇"},

    "SEA": {"emoji": "🌧", "telegram": "@Archi059", "custom_emoji_id": "5208838157931390018", "custom_emoji_fallback": "🦅"},
    "SF": {"emoji": "🌉", "telegram": "@cronnmaksim", "custom_emoji_id": "5208592288233564730", "custom_emoji_fallback": "4️⃣"},
    "LAR": {"emoji": "🐏", "telegram": "@wicked_kiD", "custom_emoji_id": "5206462469786051454", "custom_emoji_fallback": "🐏"},
    "AZ": {"emoji": "🐦", "telegram": "@Dimadontpoint", "custom_emoji_id": "5206353381911700760", "custom_emoji_fallback": "🌅"},
    "ARI": {"emoji": "🐦", "telegram": "@Dimadontpoint", "custom_emoji_id": "5206353381911700760", "custom_emoji_fallback": "🌅"},
}


def _profile_url(telegram: str) -> str:
    """@username -> t.me/username; голый числовой user_id (нет юзернейма) -> tg://user?id=..."""
    if telegram.lstrip("@").isdigit():
        return f"tg://user?id={telegram.lstrip('@')}"
    return f"https://t.me/{telegram.lstrip('@')}"


def tag(abbr: str) -> str:
    """Премиум-эмодзи с логотипом команды + HTML-ссылка на владельца (по юзернейму или user_id)."""
    t = TEAMS.get(abbr.upper())
    if not t:
        return abbr.upper()
    link = f'<a href="{_profile_url(t["telegram"])}">{abbr.upper()}</a>'
    emoji_id = t.get("custom_emoji_id")
    if not emoji_id:
        return link
    fallback = t.get("custom_emoji_fallback") or "🏈"
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji> {link}'
