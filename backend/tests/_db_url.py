"""
tests/_db_url.py — 测试数据库 URL 安全派生 helper

议题:T-1102 议题 C — `conftest.py:25` 与 `test_notifications.py:93` 双处硬编码
`settings.database_url.replace("/aipm_db", "/aipm_db_test")`,在 DB 名不是
`aipm_db` 时(如 `qiaocai` / 用户自定义),replace 不命中,TEST_DATABASE_URL
落到生产库,`Base.metadata.drop_all` 会清生产表 —— 红线风险。

本 helper 用 sqlalchemy.engine.url.make_url 安全解析 URL,精确替换 database
字段,并加 production-同名防御性 assert。
"""

from __future__ import annotations

from sqlalchemy.engine.url import URL, make_url


def derive_test_database_url(source_url: str, suffix: str = "_test") -> str:
    """
    从生产/开发 DATABASE_URL 派生测试库 URL。

    - 用 sqlalchemy.engine.url.make_url 解析 URL 结构(driver + user + host + port + database + query)。
    - 精确替换 database 字段为 `<orig>{suffix}`,其他字段全保留。
    - 防御性 assert:派生的 test_db_name 必须 != 原 db_name(否则 raise RuntimeError 拒绝运行)。
    - 若 source_url 的 database 字段为空(异常情况),raise RuntimeError 告知用户 DATABASE_URL 不完整。

    Args:
        source_url: 形如 "postgresql+asyncpg://user:pwd@host:port/dbname[?params]"
        suffix: 测试库名后缀,默认 "_test"

    Returns:
        派生后的测试库 URL 字符串(driver / user / host / port / query 完全保留,仅 database 字段替换)。

    Raises:
        RuntimeError: source_url 的 database 字段为空,或派生后的 test_db_name == orig_db_name。
    """
    url: URL = make_url(source_url)
    if not url.database:
        raise RuntimeError(
            "DATABASE_URL 不包含 database 字段,无法派生测试库 URL。"
            f"实际收到的 URL(已掩码): {url.set(password='***')!s}"
        )
    test_db_name = f"{url.database}{suffix}"
    if test_db_name == url.database:
        raise RuntimeError(f"拒绝以生产 URL 作为测试 URL:派生后的 test database name 与源相同 ({url.database!r})。")
    return url.set(database=test_db_name).render_as_string(hide_password=False)
