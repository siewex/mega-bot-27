"""Генерирует нейтральные нелоготипные заглушки logos/{ABBR}.png — просто круг в
акцентном цвете команды, без каких-либо эмблем.

Чтобы вставить настоящий логотип — положи свой PNG (с прозрачным фоном, квадратный,
любой стороны ~200px) поверх любого файла в этой папке, назвав его точно так же
(например logos/PIT.png). scorecard.py сам подхватит его при следующей отправке
recap — ничего перезапускать/перекомпилировать не нужно.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image, ImageDraw

from scorecard import TEAM_COLORS

OUT_DIR = Path(__file__).parent
SIZE = 200


def main() -> None:
    for abbr, (primary, accent) in TEAM_COLORS.items():
        img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse([6, 6, SIZE - 6, SIZE - 6], fill=accent, outline=primary, width=10)
        img.save(OUT_DIR / f"{abbr}.png")
    print(f"Готово: {len(TEAM_COLORS)} заглушек сохранено в {OUT_DIR}")


if __name__ == "__main__":
    main()
