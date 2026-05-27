from __future__ import annotations

import os
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT_NAME = "NotoSansSC"
DEFAULT_FONT_PATH = Path(__file__).resolve().parent / "fonts/NotoSansSC-Regular.ttf"
FONT_PATH = Path(os.getenv("AIPM_EXPORT_FONT_PATH", DEFAULT_FONT_PATH))


def _ensure_font() -> str:
    font_path = Path(FONT_PATH)
    if not font_path.exists():
        raise RuntimeError("请先运行 fetch_export_font.py 下载 PDF 中文字体")

    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME, str(font_path)))

    return FONT_NAME
