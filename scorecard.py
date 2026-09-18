"""Рендер PNG-карточки со счётом матча (в стиле спортивных скорбордов) — Pillow.

Логотипы команд не рисуем (чужие товарные знаки), только фирменные цвета и названия —
это публичная информация о брендах NFL, не проприетарные данные лиги.
"""
import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS_DIR = Path(__file__).parent / "fonts"
FONT_BOLD = FONTS_DIR / "PTSans-Bold.ttf"
FONT_REGULAR = FONTS_DIR / "PTSans-Regular.ttf"

# (основной цвет, акцентный цвет) — официальные цвета брендов команд NFL.
TEAM_COLORS: dict[str, tuple[str, str]] = {
    "PIT": ("#101820", "#FFB612"),
    "CIN": ("#000000", "#FB4F14"),
    "CLE": ("#311D00", "#FF3C00"),
    "BAL": ("#241773", "#9E7C0C"),
    "NE": ("#002244", "#C60C30"),
    "MIA": ("#008E97", "#FC4C02"),
    "BUF": ("#00338D", "#C60C30"),
    "NYJ": ("#125740", "#FFFFFF"),
    "TEN": ("#0C2340", "#4B92DB"),
    "IND": ("#002C5F", "#A2AAAD"),
    "HOU": ("#03202F", "#A71930"),
    "JAX": ("#101820", "#D7A22A"),
    "LV": ("#000000", "#A5ACAF"),
    "DEN": ("#002244", "#FB4F14"),
    "LAC": ("#0080C6", "#FFC20E"),
    "KC": ("#E31837", "#FFB81C"),
    "MIN": ("#4F2683", "#FFC62F"),
    "DET": ("#0076B6", "#B0B7BC"),
    "CHI": ("#0B162A", "#C83803"),
    "GB": ("#203731", "#FFB612"),
    "PHI": ("#004C54", "#A5ACAF"),
    "NYG": ("#0B2265", "#A71930"),
    "WAS": ("#5A1414", "#FFB612"),
    "DAL": ("#041E42", "#869397"),
    "ATL": ("#A71930", "#000000"),
    "TB": ("#D50A0A", "#34302B"),
    "CAR": ("#0085CA", "#101820"),
    "NO": ("#101820", "#D3BC8D"),
    "SEA": ("#002244", "#69BE28"),
    "SF": ("#AA0000", "#B3995D"),
    "LAR": ("#003594", "#FFA300"),
    "AZ": ("#97233F", "#FFFFFF"),
    "ARI": ("#97233F", "#FFFFFF"),
}

TEAM_NAMES: dict[str, str] = {
    "PIT": "STEELERS", "CIN": "BENGALS", "CLE": "BROWNS", "BAL": "RAVENS",
    "NE": "PATRIOTS", "MIA": "DOLPHINS", "BUF": "BILLS", "NYJ": "JETS",
    "TEN": "TITANS", "IND": "COLTS", "HOU": "TEXANS", "JAX": "JAGUARS",
    "LV": "RAIDERS", "DEN": "BRONCOS", "LAC": "CHARGERS", "KC": "CHIEFS",
    "MIN": "VIKINGS", "DET": "LIONS", "CHI": "BEARS", "GB": "PACKERS",
    "PHI": "EAGLES", "NYG": "GIANTS", "WAS": "COMMANDERS", "DAL": "COWBOYS",
    "ATL": "FALCONS", "TB": "BUCCANEERS", "CAR": "PANTHERS", "NO": "SAINTS",
    "SEA": "SEAHAWKS", "SF": "49ERS", "LAR": "RAMS", "AZ": "CARDINALS", "ARI": "CARDINALS",
}

WIDTH, HEIGHT = 1000, 420
HEADER_H = 70
ROW_H = 150
PAD = 28


@lru_cache(maxsize=32)
def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), size)


def _team_row(draw: ImageDraw.ImageDraw, y: int, abbr: str, score: int) -> None:
    primary, accent = TEAM_COLORS.get(abbr, ("#2b2b2b", "#cccccc"))
    name = TEAM_NAMES.get(abbr, abbr)

    draw.rectangle([0, y, WIDTH, y + ROW_H], fill=primary)
    draw.rectangle([0, y, 14, y + ROW_H], fill=accent)

    draw.text((PAD + 20, y + 22), abbr, font=_font(30), fill=accent)
    draw.text((PAD + 20, y + 62), name, font=_font(56), fill="#FFFFFF")

    score_text = str(score)
    score_font = _font(90)
    bbox = draw.textbbox((0, 0), score_text, font=score_font)
    tw = bbox[2] - bbox[0]
    draw.text((WIDTH - PAD - tw, y + (ROW_H - (bbox[3] - bbox[1])) // 2 - bbox[1]), score_text, font=score_font, fill="#FFFFFF")


def render_scorecard(week: str, away: str, home: str, away_score: int, home_score: int) -> bytes:
    img = Image.new("RGB", (WIDTH, HEIGHT), "#15181D")
    draw = ImageDraw.Draw(img)

    draw.rectangle([0, 0, WIDTH, HEADER_H], fill="#1E2229")
    title = f"MEGA · Неделя {week}" if week and week != "?" else "MEGA"
    draw.text((PAD, 18), title, font=_font(32), fill="#FFFFFF")

    badge_font = _font(26)
    badge_text = "FINAL"
    bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    bw, bh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    badge_pad_x, badge_pad_y = 18, 10
    bx1 = WIDTH - PAD - bw - 2 * badge_pad_x
    draw.rounded_rectangle(
        [bx1, 14, WIDTH - PAD, 14 + bh + 2 * badge_pad_y],
        radius=8, fill="#FFB612",
    )
    draw.text((bx1 + badge_pad_x, 14 + badge_pad_y - bbox[1]), badge_text, font=badge_font, fill="#101820")

    _team_row(draw, HEADER_H, away, away_score)
    _team_row(draw, HEADER_H + ROW_H, home, home_score)

    footer_y = HEADER_H + 2 * ROW_H
    draw.rectangle([0, footer_y, WIDTH, HEIGHT], fill="#1E2229")
    draw.text((PAD, footer_y + (HEIGHT - footer_y - 22) // 2), "MEGA League · Madden 27", font=_font(22), fill="#8A8F98")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
