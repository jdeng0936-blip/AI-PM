"""Download the Phase 8 export PDF Chinese font.

The font binary is intentionally not committed. Run this script once after
installing dependencies and before generating PDF exports.
"""

from __future__ import annotations

import hashlib
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PRIMARY_URL = (
    "https://cdn.jsdelivr.net/gh/notofonts/notofonts.github.io@main/" "fonts/NotoSansSC/full/ttf/NotoSansSC-Regular.ttf"
)

# The primary notofonts.github.io package may exceed jsDelivr's package-size
# limit. This fallback is still served by jsDelivr and is an official Noto CJK
# Simplified Chinese TrueType font.
FALLBACK_URL = "https://cdn.jsdelivr.net/gh/notofonts/noto-cjk@main/" "Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf"

EXPECTED_SHA256 = "d68bafcb48a2707749396aa12bbbd833cb70401f3a9a689fd2902c7e0d295964"
MIN_FONT_BYTES = 1_000_000
TARGET = Path(__file__).resolve().parent.parent / "app/services/export/fonts/NotoSansSC-Regular.ttf"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, target: Path) -> None:
    request = Request(url, headers={"User-Agent": "AI-PM export font fetcher"})
    with urlopen(request, timeout=60) as response:
        data = response.read()

    if len(data) < MIN_FONT_BYTES:
        raise RuntimeError(f"下载内容过小,不像字体文件: {len(data)} bytes")

    target.write_bytes(data)


def _download_with_fallback(temp_path: Path) -> str:
    errors: list[str] = []
    for url in (PRIMARY_URL, FALLBACK_URL):
        try:
            _download(url, temp_path)
        except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
            errors.append(f"{url} -> {exc}")
            continue
        return url

    raise RuntimeError("字体下载失败:\n" + "\n".join(errors))


def main() -> int:
    if TARGET.exists():
        actual = _sha256(TARGET)
        if actual == EXPECTED_SHA256:
            print(f"字体已存在且 SHA256 校验通过: {TARGET}")
            return 0
        print(f"已有字体 SHA256 不匹配,将重新下载: {actual}")

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        temp_path = Path(tmp.name)

    try:
        source_url = _download_with_fallback(temp_path)
        actual = _sha256(temp_path)
        if actual != EXPECTED_SHA256:
            raise RuntimeError(f"字体 SHA256 校验失败: expected={EXPECTED_SHA256}, actual={actual}")
        temp_path.replace(TARGET)
    finally:
        if temp_path.exists():
            temp_path.unlink()

    print(f"字体下载完成: {TARGET}")
    print(f"来源: {source_url}")
    print(f"SHA256: {EXPECTED_SHA256}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"导出字体获取失败: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
