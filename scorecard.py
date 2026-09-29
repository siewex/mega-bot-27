"""Рендер PNG-карточки GAME RECAP в стиле glass (Pillow).

Макет «лицом к лицу»: слева гости, справа хозяева, крупный счёт по центру, ниже
лучшие игроки друг напротив друга по категориям. Карточка из «матового стекла»
лежит на размытых огнях в цветах обеих команд — фон рисуется самим кодом.

Логотипы берутся из logos/{ABBR}.png, если файл там есть (кладёт владелец бота
сам); иначе на месте логотипа ничего не рисуется.
"""
import io
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from boxscore import _guess_category

FONTS_DIR = Path(__file__).parent / "fonts"
FONT_BOLD = FONTS_DIR / "PTSans-Bold.ttf"
FONT_REGULAR = FONTS_DIR / "PTSans-Regular.ttf"
LOGOS_DIR = Path(__file__).parent / "logos"

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

CATS = [("pass", "ПАС"), ("rush", "ВЫНОС"), ("rec", "ПРИЁМ"), ("def", "ЗАЩИТА")]

W = 1200            # ширина самой карточки
PAD = 60            # поля фона вокруг карточки
HDR, BAND, ROW, BOTTOM = 72, 220, 88, 14
RADIUS = 26
CENTER = 176        # ширина центральной колонки с категориями
LOGO = 124
DARK_ACCENTS = {"#000000", "#101820", "#34302B"}


@lru_cache(maxsize=64)
def _font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT_REGULAR), size)


def _logo(abbr: str) -> Image.Image | None:
    """Логотип перечитывается, если файл добавили/заменили — без перезапуска бота."""
    path = LOGOS_DIR / f"{abbr}.png"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    return _load_logo(str(path), mtime)


@lru_cache(maxsize=64)
def _load_logo(path: str, mtime: float) -> Image.Image | None:
    try:
        im = Image.open(path).convert("RGBA")
    except Exception:
        return None
    im.thumbnail((LOGO, LOGO))
    return im


def _tw(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int, int]:
    b = draw.textbbox((0, 0), text, font=font)
    return b[2] - b[0], b[3] - b[1], b[1]


def _fit(draw: ImageDraw.ImageDraw, text: str, max_w: int, size: int, bold: bool = True):
    while size > 12 and _tw(draw, text, _font(size, bold))[0] > max_w:
        size -= 2
    return _font(size, bold)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    return tuple(int(hex_color[k:k + 2], 16) for k in (1, 3, 5))


def _colors(abbr: str) -> tuple[str, str]:
    return TEAM_COLORS.get(abbr, ("#2B2B2B", "#CCCCCC"))


def _layer_rect(img: Image.Image, box, fill, radius: int = 0, outline=None, width: int = 1) -> None:
    """Полупрозрачный прямоугольник: ImageDraw по RGBA заменяет пиксели, а не смешивает."""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)
    img.alpha_composite(layer)


def _gradient_band(img: Image.Image, box, color: str, a_outer: int, a_inner: int, outer_left: bool) -> None:
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    grad = Image.linear_gradient("L").rotate(90 if outer_left else -90, expand=True).resize((w, h))
    grad = grad.point(lambda v: int(a_inner + (a_outer - a_inner) * v / 255))
    band = Image.new("RGBA", (w, h), _rgb(color) + (0,))
    band.putalpha(grad)
    img.alpha_composite(band, (x0, y0))


def _bokeh(w: int, h: int, away: str, home: str) -> Image.Image:
    """Размытые огни: слева в цветах гостей, справа — хозяев. Сид от матча, чтобы
    одна и та же игра всегда рисовалась одинаково."""
    rnd = random.Random(f"{away}@{home}")
    bg = Image.new("RGBA", (w, h), "#0F1115")
    (ap, aa), (hp, ha) = _colors(away), _colors(home)
    palettes = ([ap, aa], [hp, ha])
    for i in range(34):
        r = rnd.randint(60, 220)
        left = i % 2 == 0
        x = rnd.randint(0, w // 2) if left else rnd.randint(w // 2, w)
        y = rnd.randint(0, h)
        col = palettes[0 if left else 1][rnd.randint(0, 1)]
        _layer_rect(bg, [x - r, y - r, x + r, y + r], _rgb(col) + (rnd.randint(70, 150),), radius=r)
    return bg.filter(ImageFilter.GaussianBlur(40))


def _by_cat(stats: list[tuple[str, str]]) -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    for name, line in stats:
        out.setdefault(_guess_category(line), (name, line))
    return out


def _team_band(img: Image.Image, x0: int, y: int, side: str, abbr: str, score: int, won: bool) -> None:
    prim, acc = _colors(abbr)
    bx0, bx1 = (x0, x0 + W // 2) if side == "L" else (x0 + W // 2, x0 + W)
    _gradient_band(img, (bx0, y, bx1, y + BAND), prim, 215 if won else 140, 95 if won else 45, side == "L")
    _layer_rect(img, [bx0, y + BAND - 6, bx1, y + BAND], _rgb(acc) + (235 if won else 150,))

    d = ImageDraw.Draw(img)
    txt = "#FFFFFF" if won else "#B9BEC6"
    acc_txt = acc if acc not in DARK_ACCENTS else "#D0D3D8"
    cy = y + BAND // 2
    sf = _font(124)
    sw, sh, so = _tw(d, str(score), sf)
    if side == "L":
        lx, sx = x0 + 34, x0 + W // 2 - 44 - sw
        nx = lx + LOGO + 20
        name_max = sx - nx - 20
    else:
        lx, sx = x0 + W - 34 - LOGO, x0 + W // 2 + 44
        name_max = lx - 20 - (sx + sw + 20)

    lg = _logo(abbr)
    if lg is not None:
        if not won:
            lg = Image.blend(Image.new("RGBA", lg.size, (0, 0, 0, 0)), lg, 0.75)
        img.alpha_composite(lg, (lx + (LOGO - lg.width) // 2, cy - lg.height // 2))
        d = ImageDraw.Draw(img)

    d.text((sx, cy - sh // 2 - so), str(score), font=sf, fill=txt)
    name = TEAM_NAMES.get(abbr, abbr)
    nf = _fit(d, name, name_max, 44)
    af = _font(24)
    if side == "L":
        d.text((nx, cy - 42), abbr, font=af, fill=acc_txt)
        d.text((nx, cy - 10), name, font=nf, fill=txt)
    else:
        rx = lx - 20
        d.text((rx - _tw(d, abbr, af)[0], cy - 42), abbr, font=af, fill=acc_txt)
        d.text((rx - _tw(d, name, nf)[0], cy - 10), name, font=nf, fill=txt)


def render_scorecard(
    week: str, away: str, home: str, away_score: int, home_score: int,
    away_stats: list[tuple[str, str]] | None = None,
    home_stats: list[tuple[str, str]] | None = None,
) -> bytes:
    away_c, home_c = _by_cat(away_stats or []), _by_cat(home_stats or [])
    rows = [(cat, label) for cat, label in CATS if cat in away_c or cat in home_c]
    ch = HDR + BAND + ROW * len(rows) + BOTTOM
    img = _bokeh(W + PAD * 2, ch + PAD * 2, away, home)
    x0, y0, x1, y1 = PAD, PAD, PAD + W, PAD + ch

    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([x0 + 4, y0 + 16, x1 + 4, y1 + 16], radius=RADIUS, fill=(0, 0, 0, 150))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))

    frosted = img.crop((x0, y0, x1, y1)).filter(ImageFilter.GaussianBlur(24))
    frosted.alpha_composite(Image.new("RGBA", frosted.size, (255, 255, 255, 18)))
    frosted.alpha_composite(Image.new("RGBA", frosted.size, (10, 12, 16, 120)))
    mask = Image.new("L", frosted.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, W, ch], radius=RADIUS, fill=255)
    img.paste(frosted, (x0, y0), mask)

    d = ImageDraw.Draw(img)
    title = f"MEGA · Неделя {week}" if week and week != "?" else "MEGA"
    d.text((x0 + 32, y0 + 20), title, font=_font(30), fill="#FFFFFF")
    bf = _font(24)
    bw, bh, bo = _tw(d, "FINAL", bf)
    bx = x1 - 32 - bw - 36
    d.rounded_rectangle([bx, y0 + 18, x1 - 32, y0 + 36 + bh], radius=16, fill="#FFB612")
    d.text((bx + 18, y0 + 27 - bo), "FINAL", font=bf, fill="#101820")

    # При ничьей обе стороны яркие — приглушаем только проигравшего.
    away_won = away_score >= home_score
    home_won = home_score >= away_score
    by = y0 + HDR
    _team_band(img, x0, by, "L", away, away_score, away_won)
    _team_band(img, x0, by, "R", home, home_score, home_won)
    _layer_rect(img, [x0 + W // 2 - 1, by, x0 + W // 2 + 1, by + BAND], (255, 255, 255, 60))

    sy = by + BAND
    for i, (cat, label) in enumerate(rows):
        y = sy + i * ROW
        if i:
            _layer_rect(img, [x0 + 30, y, x1 - 30, y + 1], (255, 255, 255, 30))
        pill = [x0 + W // 2 - CENTER // 2, y + ROW // 2 - 18, x0 + W // 2 + CENTER // 2, y + ROW // 2 + 18]
        _layer_rect(img, pill, (255, 255, 255, 26), radius=18, outline=(255, 255, 255, 70), width=1)
        d = ImageDraw.Draw(img)
        lf = _font(19)
        lw, lh, lo = _tw(d, label, lf)
        d.text((x0 + W // 2 - lw // 2, y + ROW // 2 - lh // 2 - lo), label, font=lf, fill="#E6E8EB")
        for side, stat, won in (("L", away_c.get(cat), away_won), ("R", home_c.get(cat), home_won)):
            if not stat:
                continue
            name, line = stat
            max_w = W // 2 - CENTER // 2 - 64
            nf, lf2 = _fit(d, name, max_w, 25), _fit(d, line, max_w, 20, bold=False)
            ncol = "#FFFFFF" if won else "#C4C8CE"
            if side == "L":
                right = x0 + W // 2 - CENTER // 2 - 30
                d.text((right - _tw(d, name, nf)[0], y + 14), name, font=nf, fill=ncol)
                d.text((right - _tw(d, line, lf2)[0], y + 48), line, font=lf2, fill="#A7ADB5")
            else:
                left = x0 + W // 2 + CENTER // 2 + 30
                d.text((left, y + 14), name, font=nf, fill=ncol)
                d.text((left, y + 48), line, font=lf2, fill="#A7ADB5")

    _layer_rect(img, [x0, y0, x1, y1], (0, 0, 0, 0), radius=RADIUS, outline=(255, 255, 255, 75), width=2)

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()
