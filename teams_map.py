"""Команды лиги: эмодзи + телеграм-аккаунт менеджера. Ключи — аббревиатуры madden.tools/MTFranchiseBot."""

TEAMS = {
    "PIT": {"emoji": "👷‍♂️", "telegram": "@kislik34"},
    "CIN": {"emoji": "🐅", "telegram": "@Asttema"},
    "CLE": {"emoji": "🤎", "telegram": "@lespaul88"},
    "BAL": {"emoji": "🦉", "telegram": "@Arturetti"},

    "NE": {"emoji": "💂", "telegram": "@fnolzoar"},
    "MIA": {"emoji": "🐬", "telegram": "@l3dn1q"},
    "BUF": {"emoji": "🐂", "telegram": "@DaniVRN"},
    "NYJ": {"emoji": "✈️", "telegram": "@Ajoudojuau"},

    "TEN": {"emoji": "⚔️", "telegram": "@kkkkkk13_13"},
    "IND": {"emoji": "🧲", "telegram": "@GilTimRus"},
    "HOU": {"emoji": "🇨🇱", "telegram": "@Imam"},
    "JAX": {"emoji": "😾", "telegram": "@StasVII"},

    "LV": {"emoji": "☠️", "telegram": "@Hvosssteg"},
    "DEN": {"emoji": "🐎", "telegram": "@DrobiazgoD"},
    "LAC": {"emoji": "⚡️", "telegram": "@dail87"},
    "KC": {"emoji": "🏹", "telegram": "@mahomes15"},

    "MIN": {"emoji": "🇦🇽", "telegram": "@MarcusHoper"},
    "DET": {"emoji": "🦁", "telegram": "@mishgek"},
    "CHI": {"emoji": "🐻", "telegram": "@MikeRyabikin"},
    "GB": {"emoji": "📦", "telegram": "@harley47"},

    "PHI": {"emoji": "🦅", "telegram": "@bernikoww"},
    "NYG": {"emoji": "🏙", "telegram": "@defisparta"},
    "WAS": {"emoji": "🫡", "telegram": "@Laruzz"},
    "DAL": {"emoji": "🤠", "telegram": "@Chippolllino"},

    "ATL": {"emoji": "🪶", "telegram": "@Oleg_Oleynikov"},
    "TB": {"emoji": "🏴‍☠️", "telegram": "@teodossi"},
    "CAR": {"emoji": "🐈‍⬛️", "telegram": "@udzhinable"},
    "NO": {"emoji": "⚜️", "telegram": "@ellwoood"},

    "SEA": {"emoji": "🌧", "telegram": "@Archi059"},
    "SF": {"emoji": "🌉", "telegram": "@cronnmaksim"},
    "LAR": {"emoji": "🐏", "telegram": "@wicked_kiD"},
    "AZ": {"emoji": "🐦", "telegram": "@Dimadontpoint"},
    "ARI": {"emoji": "🐦", "telegram": "@Dimadontpoint"},
}


def tag(abbr: str) -> str:
    """HTML-ссылка на аббревиатуре команды, ведущая на t.me/<хендл> её владельца."""
    t = TEAMS.get(abbr.upper())
    if not t:
        return abbr.upper()
    handle = t["telegram"].lstrip("@")
    return f'<a href="https://t.me/{handle}">{abbr.upper()}</a>'
