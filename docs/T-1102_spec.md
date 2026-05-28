# T-1102 实施契约:测试隔离污染 + 配置漂移修复(议题 A + B + C 三合一)

> **指挥官签字时间戳**:`[2026-05-28 17:21:38]`
> **持牌任务**:Phase 11 **第二任** — 测试隔离 + 配置漂移仓库层面修复
> **触发来源**:T-1101 二次验收时(`[2026-05-28 16:03]`)实测 `pytest -q` 跑出 `1 failed / 177 passed / 2 skipped`,以及指挥官 T-1101 执行过程中发现的 `backend/.env` 漂移 + `conftest.py:25` 硬编码隐患。看板 `dev_tasks.md` L229-238 已锁定 3 个候选议题(A 测试隔离污染 / B `.env.example` 配置漂移 / C `conftest.py:25` 隐患),本契约把 C 议题从「留待 T-1103」升级为 T-1102 主线 —— **三议题一次性收口**,因为它们都是**测试基线稳健化**的同一根因(测试自治 + 配置一致 + DB URL 安全派生)。
> **范围**:**测试代码 + 文档为主,零业务 src(`backend/app/`)改动**。

---

## §1 任务概述

T-1101 闭环后,Phase 10 / 11 测试基线遗留 3 类**结构性**问题:

### 议题 A:`test_notifications.py::test_notify_unconfigured_channels_skipped` 测试自治缺失

**症状**:`pytest -q` 全套跑出 1 failed(本机指挥官 `[2026-05-28 16:03]` 实测);Codex 通过"进程级清空 `WECHAT_BOT_WEBHOOK / DINGTALK_BOT_WEBHOOK / SMTP_*` 等 env"绕过(达成 `178 passed`)。

**根因**:`test_notifications.py:140` 测试断言"企微/钉钉**未配置**时通知应 skipped"。但测试**不**主动清空 `settings.wechat_bot_webhook / dingtalk_bot_webhook / smtp_server` 等通道配置,直接依赖**跑测试者本机 `.env` 是否已配置**这些通道。若本机 `.env` 配了真实 Webhook,`settings.wechat_bot_webhook` 非空,`notify_service` 内部会试着发出真实请求(或 404 或 500),`records[].status` 不再单调落在 `(skipped, failed)` 任一,导致 assert 失败。

**根本修复**:用 `monkeypatch.setattr(settings, ..., "")` 在测试入口**主动清空**通道配置,让测试**完全自管 isolation**,不依赖跑测试者 env 状态。

### 议题 B:`backend/.env.example` 兼容别名漂移 + 开发环境启动文档缺最小必填清单

**症状**:`backend/app/config.py` 用 `AliasChoices(...)` 给多个字段加了**兼容别名**(`WECOM_*` ↔ `WECHAT_*` / `MAIL_*` ↔ `SMTP_*` / `LITELLM_*` ↔ `NEW_API_*` / `OSS_ACCESS_KEY_ID/BUCKET_NAME/ACCESS_KEY_SECRET` ↔ `OSS_*`),但 `backend/.env.example` 仅列**主名**,**未在注释中标注兼容别名**。新接入开发者按各种历史文档或第三方教程填 `WECOM_CORP_ID` / `MAIL_SERVER` / `LITELLM_API_KEY` 时,`config.py` 能正确解析,但 `.env.example` 不告诉他**也可以**,导致**配置混乱**(部分用主名、部分用别名,审计时混乱)。

**症状 2**:README.md L24-50「开发环境启动」段没有「最小必填 env 项」清单(只笼统说"编辑 .env,填写企微 / NewApi / 数据库连接等配置"),新接入开发者很可能漏配 `JWT_SECRET_KEY`(`config.py:112` 无默认值,pydantic 必填,缺会 `ValidationError`,而错误信息对新手并不友好)+ `DATABASE_URL`(同上)。

**根本修复**:`.env.example` 在主名注释行加 `// 兼容别名:XXX` 标注;README.md「开发环境启动」段加「最小必填 env 项」5 行清单 + `JWT_SECRET_KEY` 用 `openssl rand -hex 32` 生成提示。**不**改 `config.py`(`AliasChoices` 已经在做工,pydantic 必填字段缺失的 `ValidationError` 已经足够清晰,**过度封装反而增加 src 维护风险**)。

### 议题 C:`conftest.py:25` + `test_notifications.py:93` 硬编码 `replace("/aipm_db", "/aipm_db_test")` 双处隐患

**症状**(双处硬编码):

```python
# backend/tests/conftest.py:25
TEST_DATABASE_URL = os.getenv("DATABASE_URL_TEST") or settings.database_url.replace("/aipm_db", "/aipm_db_test")

# backend/tests/test_notifications.py:93(自管 engine)
TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")
```

**根因**:`.replace()` 在 URL 字符串上做盲匹配,只有 DB 名**恰好叫 `aipm_db`** 时才能正确派生出 `aipm_db_test`。若开发者本机 `DATABASE_URL` 写成:
- `postgresql+asyncpg://aipm:xx@localhost:5432/qiaocai`(自定义 DB 名) → `.replace()` **不命中**,`TEST_DATABASE_URL` **= 生产 URL**
- `postgresql+asyncpg://aipm:xx@host/aipm_db?param=...` → 还能命中(query string 不影响)

**风险等级**:**红线** —— `conftest.py` `setup_test_db` fixture 会跑 `await conn.run_sync(Base.metadata.drop_all)` 清理表。若 `TEST_DATABASE_URL` 实际指向**生产库**,**生产数据全部被 `DROP TABLE`**。本机 `pytest` 命令可一键摧毁仓库管理的任何环境。

**根本修复**:抽 helper `derive_test_database_url(source_url: str) -> str`,放在新建的 `backend/tests/_db_url.py`(供 `conftest.py` + `test_notifications.py` 共用)。用 `sqlalchemy.engine.url.make_url` 解析 URL,精确替换 `database` 字段为 `<orig>_test`,并加 **production-同名保护**:若派生出的 test DB 名 = 源 DB 名(理论不会发生,但做防御性 assert),`raise RuntimeError("拒绝以生产 URL 作为测试 URL")`。

---

## §2 文件范围锁定(严格 7 文件,白名单)

```
+ backend/tests/_db_url.py                  # 新建,~50 行,derive_test_database_url helper
+ backend/tests/conftest.py                 # L25 替换为 helper 调用(1 行,精确替换)
+ backend/tests/test_notifications.py       # L93 替换为 helper 调用 + L140 测试加 monkeypatch fixture
+ backend/.env.example                      # 在 5 个有 AliasChoices 别名的字段注释行加 `# 兼容别名: XXX`
+ README.md                                 # 在「开发环境启动」段后追加「最小必填 env 项」清单
+ docs/T-1102_spec.md                       # 本文件(指挥官 chore(spec) commit 已带)
+ docs/dev_tasks.md                         # Task 2 (T-1102) `[ ]` → `[/]`(本 commit 加锁)+ 📣 锚点重写
```

**严禁清单**(改动一律驳回):

- ❌ 改 `backend/app/` 任何文件(包括 `config.py` —— pydantic 必填 + AliasChoices 已经在做事,**不**叠加自定义 validator)
- ❌ 改 `backend/alembic/` 任何 migration
- ❌ 改 `frontend/` 任何文件
- ❌ 改 `backend/tests/` 上述 3 个 file 之外的任何 test
- ❌ 改 `backend/conftest.py` 之外的 `conftest.py`(若存在嵌套 conftest)
- ❌ 改 `docs/T-1XXX_spec.md` 历史契约(包括 T-1101_spec.md / T-1008_spec.md 等)
- ❌ 改 `DEPLOY.md`(已是生产部署清单,本任务只面向**本地开发**)
- ❌ 改 `backend/.env`(个人本机配置,**严禁 Agent 直接改**)
- ❌ 动 4 既定 untracked 文件(`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock`)
- ❌ 动 `.gitignore` / `.claude/` 项目级 ECC symlinks
- ❌ 自动 `git push`
- ❌ 自启 T-1103 任何后续任务
- ❌ 改 `notify_service` / 通知模板 / `Notification` model(议题 A 是**测试**自治问题,不是 service bug)

---

## §3 详细文件改动

### §3.1 新建 `backend/tests/_db_url.py`(议题 C 主修复)

**完整文件字面量**(~50 行,逐字符锁定):

```python
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
        raise RuntimeError(
            f"拒绝以生产 URL 作为测试 URL:派生后的 test database name 与源相同 ({url.database!r})。"
        )
    return str(url.set(database=test_db_name))
```

**字面量注意点**:
- `from __future__ import annotations` 必带(对齐项目其他 test file 的 style)。
- `URL` 用大写,不要换成小写或别名。
- docstring 内的「红线」/ 「防御性 assert」中文字面量保留。
- `url.set(password='***')` 用单引号(对齐项目风格),其余字符串均用双引号(对齐项目 ruff 默认)。
- 无业务依赖(纯 `sqlalchemy.engine.url`),不引入任何 `app.config` / `Base` / fixture 依赖,**保证可被任何 test 模块独立 import**。

### §3.2 改 `backend/tests/conftest.py`(议题 C 主调用)

#### §3.2.1 加 import + 替换 L25(单点修改)

**当前 L10-25 上下文**:

```python
import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app

# ── 使用独立测试数据库（生产数据库名追加 _test）──────────────────
# CI 显式传 DATABASE_URL_TEST;本地未配置时沿用历史规则。
TEST_DATABASE_URL = os.getenv("DATABASE_URL_TEST") or settings.database_url.replace("/aipm_db", "/aipm_db_test")
```

**改后**:

1. **加 import**(在 `from app.main import app` 之后插一行,与其他 from-import 块用空行分隔)。
2. **替换 L25**(整行替换,保留 L23-24 注释不变)。

```python
import asyncio
import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app

from tests._db_url import derive_test_database_url

# ── 使用独立测试数据库（生产数据库名追加 _test）──────────────────
# CI 显式传 DATABASE_URL_TEST;本地未配置时沿用历史规则。
# T-1102 议题 C:用 derive_test_database_url 替代 str.replace,
# 防御 DB 名非 `aipm_db` 时硬编码 replace 失效落到生产 URL 的风险。
TEST_DATABASE_URL = os.getenv("DATABASE_URL_TEST") or derive_test_database_url(settings.database_url)
```

**注意**:
- `from tests._db_url import derive_test_database_url`(用 **`tests.` 包路径**,因为 `backend/pyproject.toml` 把 `backend/` 作为 pytest rootdir,`tests` 是 package)。Worker 需要确认 `backend/tests/__init__.py` 是否存在;若不存在,**新建空文件** `backend/tests/__init__.py`(纳入本任务范围,作为隐式新增文件)。
- 中文注释 2 行(议题 C 解释)保留,作为修改原因审计。
- L25 之外的 L23-24 注释保持不动。

#### §3.2.2 如需:新建 `backend/tests/__init__.py`(空文件)

**仅当**前置探针 `ls backend/tests/__init__.py` 返回 not found 时,新建空文件(0 字节)。若已存在则跳过本子项。

**Worker 探针命令**:
```bash
ls backend/tests/__init__.py 2>&1
```

输出 `No such file or directory` → 新建 `backend/tests/__init__.py`(空文件)。
输出文件信息 → 跳过本子项。

### §3.3 改 `backend/tests/test_notifications.py`(议题 A + 议题 C 双修)

#### §3.3.1 替换 L93(议题 C 同步修复,单点)

**当前 L88-93**:

```python
# ────────────────────────────────────────────────────────────────
# DB 测试:自管会话(绕开 conftest 的 begin() 包裹)
# ────────────────────────────────────────────────────────────────


TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")
```

**改后**:

1. 在文件顶部 import 区(L26-33 之间,与 `from app.services.notification_service import notify, render_template` 一起;按字母序插入)加:
   ```python
   from tests._db_url import derive_test_database_url
   ```
2. 替换 L93 整行:
   ```python
   TEST_DATABASE_URL = derive_test_database_url(settings.database_url)
   ```

**注**:`tests._db_url` import 在 `from app.services.notification_service` 之后(应用 imports 完之后,**最后**再 import tests 内部 helper),保持 import 顺序整洁(`app.*` → `tests.*`)。

#### §3.3.2 加 `_clean_notification_settings` fixture(议题 A 主修复)

**位置**:`isolated_db` fixture(L96-107)**之后**追加一个新 fixture,**之前**插入(原 L110 `@pytest.mark.asyncio` 之前)。

**字面量**(逐字符锁定):

```python


@pytest.fixture(autouse=True)
def _clean_notification_settings(monkeypatch):
    """
    T-1102 议题 A:测试自治 — 主动清空所有通知通道 settings,
    让 `test_notify_unconfigured_channels_skipped` 等 case 不依赖
    跑测试者本机 `.env` 状态(否则本地配了真实 Webhook 会导致 notify
    走真实请求 → 4xx/5xx → assert 失败)。

    autouse=True 让本模块所有 DB 测试统一享受 isolation,纯 render 测试
    用不上但无副作用(monkeypatch 在 test 结束自动还原)。
    """
    monkeypatch.setattr(settings, "wechat_corp_id", "", raising=False)
    monkeypatch.setattr(settings, "wechat_corp_secret", "", raising=False)
    monkeypatch.setattr(settings, "wechat_agent_id", "", raising=False)
    monkeypatch.setattr(settings, "wechat_bot_webhook", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_bot_webhook", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_bot_secret", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_app_key", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_app_secret", "", raising=False)
    monkeypatch.setattr(settings, "dingtalk_agent_id", "", raising=False)
    monkeypatch.setattr(settings, "smtp_server", "", raising=False)
    monkeypatch.setattr(settings, "smtp_user", "", raising=False)
    monkeypatch.setattr(settings, "smtp_password", "", raising=False)
    monkeypatch.setattr(settings, "smtp_from_email", "", raising=False)
```

**字面量注意点**:
- `autouse=True` 让所有 test case 默认享受 isolation(纯 render 测试 4 个不依赖 settings,monkeypatch 无副作用)。
- `raising=False` 防御未来字段重命名(如 `wechat_corp_id` → `wecom_corp_id`)时 fixture 还能 graceful 通过,但本契约不依赖该选项的语义,纯防御。
- 顺序锁定:wechat 5 项 → dingtalk 5 项 → smtp 4 项 = 共 13 项 setattr。
- 不动 `new_api_*` / `oss_*` / `xunfei_*` / 任何**非通知通道**字段(超范围)。

#### §3.3.3(可选)若 L140 测试 `pytest -q` 仍失败的 fallback

如果加完 §3.3.2 fixture 后,`pytest -q backend/tests/test_notifications.py::test_notify_unconfigured_channels_skipped -v` **仍然失败**,Worker 应在终端打印失败 traceback,**停手等待指挥官诊断**,**不**尝试自行扩大 monkeypatch 范围或改 notify_service 逻辑。

### §3.4 改 `backend/.env.example`(议题 B 主修复)

#### §3.4.1 在 5 处有 AliasChoices 别名的字段加注释行

**精确改动列表**(逐处定位,每处新增 1 行注释):

| 位置 | 当前文本(行) | 在该行**之前**插入注释行 |
|------|-----------------|-------------------------|
| L24 `WECHAT_CORP_ID=ww_your_corp_id` | 已有 L22-23 章节注释 | **在 L24 之前**插入:`# 兼容别名(config.py AliasChoices):WECOM_CORP_ID / WECOM_SECRET / WECOM_AGENT_ID / WECOM_TOKEN / WECOM_ENCODING_AES_KEY / WECOM_BOT_WEBHOOK` |
| L45 `DINGTALK_BOT_WEBHOOK=...` | 已有 L42-44 注释 | **在 L45 之前**插入:`# 兼容别名(config.py AliasChoices):DINGTALK_WEBHOOK / DINGTALK_SECRET` |
| L56 `NEW_API_BASE_URL=...` | 已有 L55 章节注释 | **在 L56 之前**插入:`# 兼容别名(config.py AliasChoices):LITELLM_BASE_URL / LITELLM_API_KEY` |
| L92 `SMTP_SERVER=` | 已有 L90-91 注释 | **在 L92 之前**插入:`# 兼容别名(config.py AliasChoices):MAIL_SERVER / MAIL_PORT / MAIL_USERNAME / MAIL_PASSWORD / MAIL_FROM` |
| L66 `OSS_ENDPOINT=...`(已有 L65 注释 `# 兼容别名: OSS_ACCESS_KEY_ID / OSS_ACCESS_KEY_SECRET / OSS_BUCKET_NAME`) | L65 已有注释 | **不动**(已经有兼容别名注释,保留现状) |

**字面量(逐条复制粘贴)**:

```text
# 兼容别名(config.py AliasChoices):WECOM_CORP_ID / WECOM_SECRET / WECOM_AGENT_ID / WECOM_TOKEN / WECOM_ENCODING_AES_KEY / WECOM_BOT_WEBHOOK
```
```text
# 兼容别名(config.py AliasChoices):DINGTALK_WEBHOOK / DINGTALK_SECRET
```
```text
# 兼容别名(config.py AliasChoices):LITELLM_BASE_URL / LITELLM_API_KEY
```
```text
# 兼容别名(config.py AliasChoices):MAIL_SERVER / MAIL_PORT / MAIL_USERNAME / MAIL_PASSWORD / MAIL_FROM
```

**改动数**:**4 处**(每处插入 1 行),纯增量 4 行,**零删除**。L66 不动,因为已经有兼容别名注释。

### §3.5 改 `README.md`(议题 B 文档补强)

#### §3.5.1 在「开发环境启动」段 Step 1 后追加「最小必填 env 项」清单

**位置**:`README.md` L31(`# 编辑 .env，填写企微、NewApi、数据库连接等配置`)之后 / L33(`# ── Step 2: 启动本地 PostgreSQL & Redis ──────────────────────────`)之前。

**插入字面量**(逐字符锁定,**注意首尾各一个空行**):

```text

# ── 最小必填项(否则后端启动会失败) ───────────────────────────────
# 1. JWT_SECRET_KEY      — 用 `openssl rand -hex 32` 生成 32 字符随机串
# 2. DATABASE_URL        — 例:postgresql+asyncpg://aipm:devpass@localhost:5432/aipm_db
# 3. REDIS_URL           — 例:redis://localhost:6379/0
# 4. AIPM_ENV            — dev(自动建表)或 prod(必须先 alembic upgrade head)
# 5. POSTGRES_PASSWORD   — 与 DATABASE_URL 中的 pwd 字段保持一致(供 Docker Compose 启动 PG 用)
# 其余字段(企微 / 钉钉 / OSS / Sentry / NewApi)缺失时对应功能优雅降级,不阻断启动。

```

**字面量注意点**:
- 上下各 1 个空行,与 Step 1 / Step 2 块隔开。
- 6 行注释 + 1 行"其余字段..."说明 = 共 7 行实质内容。
- emoji / 表格 / 中文标点不变(对齐 README.md 现状风格)。

### §3.6 改 `docs/dev_tasks.md`(本契约 commit 一起 add)

#### §3.6.1 Task 2 (T-1102) 行 `[ ]` → `[/]`(加锁标记开工)

**位置**:`docs/dev_tasks.md` L230 `- [ ] **Task 2 (T-1102 候选 — 待指挥官起草 spec): ...**`

**改后**:
- `[ ]` → `[/]`
- 标题更新:`**Task 2 (T-1102): 测试隔离污染 + 配置漂移仓库层面修复(议题 A + B + C 三合一)** — In Progress by Codex`(去掉「候选 — 待指挥官起草 spec」,加 `— In Progress by Codex`)
- bullet 部分**整段保留**(议题 A / B / C 描述本就是 T-1102 范围,不重写)。
- 子 bullet 末尾追加:`- **完整执行契约见 docs/T-1102_spec.md**(必读,~620 行 10 章 + 📣 附录)。`

**字面量替换块(整段)**:

**当前 L230-238**:
```markdown
- [ ] **Task 2 (T-1102 候选 — 待指挥官起草 spec): 测试隔离污染 + `backend/.env.example` 配置漂移修复**(Phase 11 第二任 candidate)
  - **议题 A — 测试隔离污染**(T-1101 closure 后剩余,`[2026-05-28 16:03]` 指挥官实测):全套 `pytest -q` 跑出 **1 failed / 177 passed / 2 skipped**(`test_notifications.py::test_notify_unconfigured_channels_skipped` 在 Codex env-cleanup 前是 6 failures 之一,Codex 通过"进程级清空通知渠道 env"绕过,但**测试本身仍依赖外部环境而非 isolation 自治**)。仓库层面真正需要的是测试代码层面的 mock + isolation,而不是依赖跑测试者手动清 env。
  - **议题 B — `backend/.env` 配置漂移仓库层面修复**(原 T-1102 Option α 范围):
    - `backend/.env.example` 完整对齐 `config.py` 字段命名(`AIPM_ENV` / `SMTP_SERVER` / `WECHAT_CORP_ID` / `DINGTALK_APP_KEY` / `NEW_API_*`),并在注释中标注常见误用别名(`APP_ENV` / `SMTP_HOST` / `WECHAT_CORPID_ID` / `DING_APP_KEY` / `OPENAI_API_KEY` 等)。
    - `README.md` 或 `DEPLOY.md` 加「本地启动检查清单」段,强调 `cd backend` 工作目录 + 必填 5 项 env vars(`JWT_SECRET_KEY` / `DATABASE_URL` / `AIPM_ENV` / ...)+ Docker PG 容器端口提醒(`localhost:5434`)。
    - `backend/app/config.py` 加 startup validation:缺关键变量(`JWT_SECRET_KEY` / `DATABASE_URL`)抛带帮助文字的 `RuntimeError`,而非难懂 pydantic `ValidationError`。
  - **议题 C(隐患,留待 T-1103 单独评估)**:**`conftest.py:25`** `replace("/aipm_db", "/aipm_db_test")` 硬编码对 `qiaocai` / 非 `aipm_db` 命名的 DB 失效,测试库 URL 可能等于 production DB URL(`drop_all` 风险)。
  - **不**改 `backend/.env`(个人本机配置,**严禁 Agent 直接改**)。
  - **完整执行契约**:待 T-1102 spec 由指挥官正式起草后链接;**本 entry 仅为 backlog 占位**,**严禁** Worker 在 spec 物理落盘前自启。
```

**替换为**:
```markdown
- [/] **Task 2 (T-1102): 测试隔离污染 + 配置漂移仓库层面修复(议题 A + B + C 三合一)** — In Progress by Codex `[2026-05-28 17:21:38]`
  - **议题 A — `test_notifications.py` 测试自治**:用 `monkeypatch.setattr(settings, ...)` 主动清空 13 项通知通道 settings(wechat 5 + dingtalk 5 + smtp 4 = 13 setattr),`autouse=True` fixture 覆盖整个 test_notifications.py 模块,让测试**不依赖跑测试者本机 .env 状态**。修复 `[2026-05-28 16:03]` 实测的 1 failed (`test_notify_unconfigured_channels_skipped`)。
  - **议题 B — `backend/.env.example` 兼容别名注释 + `README.md` 最小必填 env 清单**:
    - `.env.example` 在 4 处(WECHAT / DINGTALK / NEW_API / SMTP 章节头)加 `# 兼容别名(config.py AliasChoices):XXX` 注释行(L66 OSS 已有兼容别名注释,保留不动)。
    - `README.md` Step 1 之后插入「最小必填项」7 行清单(`JWT_SECRET_KEY` + `DATABASE_URL` + `REDIS_URL` + `AIPM_ENV` + `POSTGRES_PASSWORD`,其余字段缺失时优雅降级)。
    - **不**改 `backend/app/config.py`(pydantic 必填 + AliasChoices 已生效,过度封装风险高)。
    - **不**改 `DEPLOY.md`(它是生产部署清单,本任务只面向本地开发)。
    - **不**改 `backend/.env`(个人本机配置,**严禁 Agent 直接改**)。
  - **议题 C — `conftest.py:25` + `test_notifications.py:93` 双处硬编码 `replace("/aipm_db", "/aipm_db_test")` 隐患**:抽 helper `derive_test_database_url(source_url, suffix="_test")` 到新建 `backend/tests/_db_url.py`(~50 行),用 `sqlalchemy.engine.url.make_url` 精确替换 `database` 字段 + production-同名防御性 assert,`conftest.py` + `test_notifications.py` 双调用点同步切换。
  - **不**改 `backend/app/`、`backend/alembic/`、`frontend/`、`DEPLOY.md`、`backend/.env` 任何文件。
  - **完整执行契约见 `docs/T-1102_spec.md`**(必读,~620 行 10 章 + 📣 附录)。
```

#### §3.6.2 重写 L242-end 「📣 恢复执行指令」锚点段

**位置**:`docs/dev_tasks.md` L242 起的整个「## 📣 恢复执行指令」段(包括 L242 标题行 + 后续所有 bullet + 结尾两个 `> 更新时间戳` 引用块)。

**整体替换为**(字面量,逐字符锁定,见 **§10 物理交接单 详细字面量**)。

---

## §4 执行步骤(逐步可审计)

1. **前置探针**(强制):
   ```bash
   git status --short --branch
   git log -3 --oneline
   git diff
   git diff --cached
   ls backend/tests/__init__.py 2>&1
   ```
   必须确认:HEAD = `<指挥官 chore(spec) commit 短 sha>`(本契约 commit 落地后),工作树 clean,4 既定 untracked + `.claude/` 保留。**记录** `backend/tests/__init__.py` 是否存在(决定 §3.2.2 是否需要新建)。

2. **加锁已由指挥官代办**:`docs/dev_tasks.md` L230 已经被本契约 commit 改为 `[/] In Progress by Codex`,Worker **不必再打 `chore(lock)` commit**,**直接进入步骤 3**。

3. **执行文件改动**(顺序锁定):
   1. **新建** `backend/tests/_db_url.py`(§3.1 完整字面量复制粘贴)。
   2. **可能新建** `backend/tests/__init__.py`(若步骤 1 探针返回 not found,新建空文件)。
   3. **改** `backend/tests/conftest.py`(§3.2.1 加 import + 替换 L25)。
   4. **改** `backend/tests/test_notifications.py`:
      - L26-33 import 区追加 `from tests._db_url import derive_test_database_url`(§3.3.1)。
      - 替换 L93 整行(§3.3.1)。
      - L107(`isolated_db` fixture 结束)之后 / L110(`@pytest.mark.asyncio`)之前插入 `_clean_notification_settings` fixture(§3.3.2 完整字面量)。
   5. **改** `backend/.env.example`(§3.4.1 在 4 个章节头加兼容别名注释行)。
   6. **改** `README.md`(§3.5.1 Step 1 后插入「最小必填项」清单)。

4. **闸门**(全绿才提交):
   ```bash
   cd backend
   .venv/bin/ruff check tests/_db_url.py tests/conftest.py tests/test_notifications.py
   .venv/bin/mypy tests/_db_url.py tests/conftest.py tests/test_notifications.py
   .venv/bin/pytest -q                       # 必须 178 passed, 2 skipped(从 T-1101 完工基线零回归 + test_notify_unconfigured_channels_skipped 从 fail → pass)
   .venv/bin/alembic check                   # No new upgrade operations(零 migration 改动)
   ```

5. **改动面校验**:
   ```bash
   cd ..
   git status --short
   # 期望:
   #   M backend/tests/conftest.py
   #   M backend/tests/test_notifications.py
   #   ?? backend/tests/__init__.py  (若新建)
   #   ?? backend/tests/_db_url.py
   #   M backend/.env.example
   #   M README.md
   #   M docs/dev_tasks.md  (Task 2 [/] → [x] + 📣 锚点完工时间戳更新,由 chore commit 触发)
   #   ?? 4 既定 untracked + .claude/

   git diff <feat-sha>^..<feat-sha> -- backend/app/   # 必须空(零 src)
   git diff <feat-sha>^..<feat-sha> -- backend/alembic/   # 必须空
   git diff <feat-sha>^..<feat-sha> -- frontend/   # 必须空
   git status --short | grep "^??" | grep -vE "backend/tests/(__init__|_db_url)\.py|\.claude/" | wc -l   # 必须 = 4
   ```

6. **提交 feat commit**(单一原子,5/6 文件视 `__init__.py` 是否新建):
   ```bash
   git add backend/tests/_db_url.py backend/tests/conftest.py backend/tests/test_notifications.py backend/.env.example README.md
   # 若 §3.2.2 触发新建 __init__.py:
   git add backend/tests/__init__.py
   git commit -m "fix(tests): T-1102 harden test isolation and config drift — derive_test_database_url helper + notification settings monkeypatch + .env.example aliases + README minimum env checklist

   议题 A — test_notifications.py 测试自治:
   - 加 _clean_notification_settings(autouse=True) fixture,主动 monkeypatch 13 项
     通道 settings 为空(wechat 5 + dingtalk 5 + smtp 4),覆盖整个 test_notifications.py
     模块。test_notify_unconfigured_channels_skipped 从依赖跑测试者 .env 状态变成
     完全自管 isolation,本机不再有 1 failed。

   议题 B — .env.example 兼容别名注释 + README 最小必填 env 清单:
   - .env.example 在 WECHAT/DINGTALK/NEW_API/SMTP 4 个章节头加
     '# 兼容别名(config.py AliasChoices):XXX' 注释行(L66 OSS 已有,不重复)。
   - README.md「开发环境启动」Step 1 之后插入 7 行最小必填项清单
     (JWT_SECRET_KEY / DATABASE_URL / REDIS_URL / AIPM_ENV / POSTGRES_PASSWORD)。
   - 不动 backend/app/config.py(pydantic 必填 + AliasChoices 已足够,过度封装风险高)。

   议题 C — conftest.py:25 + test_notifications.py:93 双处硬编码隐患:
   - 新建 backend/tests/_db_url.py(~50 行 derive_test_database_url helper),
     用 sqlalchemy.engine.url.make_url 精确替换 database 字段,加 production-
     同名防御性 assert。原 .replace('/aipm_db', '/aipm_db_test') 在 DB 名非
     'aipm_db' 时不命中,会让 TEST_DATABASE_URL = 生产 URL,Base.metadata.drop_all
     会清生产表 —— 红线风险根除。
   - conftest.py L25 + test_notifications.py L93 双调用点同步切换。
   - 若 backend/tests/__init__.py 不存在则新建空文件(tests package 化)。

   零 backend/app 改动 / 零 alembic 改动 / 零 frontend 改动 / 零 backend/.env 改动。

   Worker timestamp: [YYYY-MM-DD HH:MM:SS]"
   ```

7. **提交 chore(progress) commit**(改 `dev_tasks.md`):
   ```bash
   # docs/dev_tasks.md:
   #   L230 Task 2 [/] → [x]
   #   📣 锚点段在结尾追加「T-1102 完工」更新时间戳引用块
   git add docs/dev_tasks.md
   git commit -m "chore(progress): close T-1102 — Phase 11 测试隔离 + 配置漂移修复完工

   - Task 2 (T-1102) [/] → [x]
   - 议题 A:test_notify_unconfigured_channels_skipped 1 failed → 0 failed
   - 议题 B:.env.example +4 行兼容别名注释 / README.md +7 行最小必填项清单
   - 议题 C:_db_url.py helper 新增,conftest.py + test_notifications.py 双点切换
   - 改动严格 5-6 文件(根据 __init__.py 是否新建),零 src / 零 alembic / 零 frontend / 零 backend/.env

   pytest -q: 178 passed, 2 skipped(基线零回归)

   Worker timestamp: [YYYY-MM-DD HH:MM:SS]"
   ```

8. **完工汇报**(终端打印,**不要** `git push`):
   ```
   [YYYY-MM-DD HH:MM:SS] T-1102 完工,议题 A/B/C 三合一收口,pytest 1 failed → 0 failed, 178 passed + 2 skipped。等待指挥官二次验收。
   ```

---

## §5 闸门(Worker 提交前必跑)

```bash
cd backend

# ① ruff / mypy 闸门(目标 3 文件 + 新建 helper)
.venv/bin/ruff check tests/_db_url.py tests/conftest.py tests/test_notifications.py        # All passed
.venv/bin/mypy tests/_db_url.py tests/conftest.py tests/test_notifications.py              # 0 error

# ② pytest 全套闸门
.venv/bin/pytest -q                                                                          # 0 failed, 178 passed, 2 skipped

# ③ pytest 议题 A 单点验收(防止 monkeypatch 没生效)
.venv/bin/pytest -q tests/test_notifications.py::test_notify_unconfigured_channels_skipped -v
# 必须 1 passed

# ④ pytest 议题 C 单点验收(防止 _db_url helper 抽错)
.venv/bin/python -c "
from tests._db_url import derive_test_database_url
# 用例 1:标准 aipm_db
out = derive_test_database_url('postgresql+asyncpg://u:p@h:5432/aipm_db')
assert out.endswith('/aipm_db_test'), out
# 用例 2:自定义 DB 名(原 .replace 会失效的场景)
out = derive_test_database_url('postgresql+asyncpg://u:p@h:5432/qiaocai')
assert out.endswith('/qiaocai_test'), out
# 用例 3:带 query string
out = derive_test_database_url('postgresql+asyncpg://u:p@h:5432/x?sslmode=require')
assert '/x_test?' in out or out.endswith('/x_test'), out
print('derive_test_database_url helper PASS')
"
# 必须输出 'derive_test_database_url helper PASS'

# ⑤ alembic check 闸门(零 migration 改动)
.venv/bin/alembic check                                                                      # No new upgrade operations
```

**改动面校验**(全部从仓库根执行):

```bash
cd ..

# 严格文件清单(feat commit 必须改 5-6 文件,不多不少)
git diff <feat-sha>^..<feat-sha> --name-only
# 期望(若 __init__.py 已存在):
#   backend/.env.example
#   backend/tests/_db_url.py
#   backend/tests/conftest.py
#   backend/tests/test_notifications.py
#   README.md
# 期望(若 __init__.py 新建):
#   上述 5 文件 + backend/tests/__init__.py = 6 文件

# 零 src 闸门
git diff <feat-sha>^..<feat-sha> -- backend/app/ backend/alembic/ frontend/ DEPLOY.md backend/.env       # 必须完全空

# 4 既定 untracked + .claude/ 闸门
git status --short | grep "^??" | grep -vE "^\?\? \.claude/$" | wc -l     # 必须 = 4
```

---

## §6 防越界红线(25 项,任何一项触发立即驳回)

1. ❌ 改 `backend/app/` 任何文件(含 `config.py`)
2. ❌ 改 `backend/alembic/` 任何 migration
3. ❌ 改 `backend/conftest.py` 主体之外的任何 conftest(若存在嵌套)
4. ❌ 改 `backend/tests/` 上述白名单 3 文件 + `_db_url.py` + `__init__.py` 之外的任何 test
5. ❌ 改 `frontend/` 任何文件
6. ❌ 改 `DEPLOY.md`(本任务面向本地开发,不重写生产部署清单)
7. ❌ 改 `backend/.env`(个人本机配置,**严禁 Agent 直接改**)
8. ❌ 改任何 `docs/T-1XXX_spec.md` 历史契约
9. ❌ 自动 `git push`
10. ❌ 自启 T-1103 任何后续任务
11. ❌ revert `8459a5b` / `b5e77c3` / `1c67bd4` / `19ac08e` / `8d69ca8` 任何 commit
12. ❌ 在 feat / chore commit 之外打额外提交(`chore(lock)` 已由指挥官代办,Worker 不必再加锁)
13. ❌ 篡改 §3.1 `_db_url.py` 字面量(包括函数签名 / 默认 suffix / docstring / RuntimeError 字面量)
14. ❌ 把 `derive_test_database_url` 改为 lambda / inline expression(必须独立函数,可被双调用点 import)
15. ❌ 在 `_db_url.py` 内 import `app.config` / `Base` / `settings`(必须**纯 sqlalchemy.engine.url** 依赖,保证可独立 import)
16. ❌ 篡改 §3.3.2 `_clean_notification_settings` fixture 字面量(包括 13 项 setattr 列表)
17. ❌ 把 fixture 改为 `autouse=False` 或非 `monkeypatch.setattr`(必须 autouse=True + monkeypatch 才能 module-wide isolation + 自动还原)
18. ❌ 给 `_clean_notification_settings` 加超范围 setattr(`new_api_*` / `oss_*` / `xunfei_*` / `jwt_*` 等非通知通道字段不允许)
19. ❌ 给 `notify_service` 加防御性代码(议题 A 是测试问题,不是 service bug)
20. ❌ 在 `.env.example` 中**删除任何**现有行或调换顺序(只能纯**插入** 4 行注释)
21. ❌ 在 `README.md` 中**删除**任何现有行或重写开发环境启动整段(只能在 Step 1 / Step 2 之间纯插入 7 行 + 上下空行)
22. ❌ 改 `docs/dev_tasks.md` Phase 9 / Phase 10 段落 / 质量闸门 / 执行协议提醒等任何**非 Phase 11 任务看板 + 📣 锚点**的内容
23. ❌ 在 commit message 中省略 `Worker timestamp:` 行
24. ❌ 写极简一行 commit message(必须 multi-line body,对比 T-1005/T-1007/T-1008 风格)
25. ❌ 动 4 既定 untracked 文件(`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock`)+ `.claude/` 项目级 ECC symlinks

---

## §7 commit message 序列(逐条字面量)

**Commit 1**(feat,改 5-6 文件):

```
fix(tests): T-1102 harden test isolation and config drift — derive_test_database_url helper + notification settings monkeypatch + .env.example aliases + README minimum env checklist

[完整 body 见 §4 Step 6]

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

**Commit 2**(chore,改 `dev_tasks.md`):

```
chore(progress): close T-1102 — Phase 11 测试隔离 + 配置漂移修复完工

[完整 body 见 §4 Step 7]

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

**严禁**:仅一行 commit message(对比 T-1005/T-1007/T-1008 的 multi-line body 风格,**收紧审计可读性**)。**严禁**省略 `Worker timestamp:` 行。

---

## §8 验收清单(指挥官二次验收用,22 项)

| # | 项 | 通过条件 |
|---|---|---|
| 1 | commit 链路 | HEAD 在 chore(spec): T-1102 契约起草 commit 之后 = 2 个 Worker commit(feat + chore) |
| 2 | feat commit 文件数 | 严格 = 5 或 6 文件(根据 `backend/tests/__init__.py` 是否新建),无第七个文件夹带 |
| 3 | chore commit 文件数 | 严格 = 1 文件(`docs/dev_tasks.md`),无其他夹带 |
| 4 | 零 src 改动 | `git diff <feat>^..<feat> -- backend/app/ backend/alembic/ frontend/ DEPLOY.md backend/.env` 完全空 |
| 5 | `_db_url.py` 字面量 | grep `def derive_test_database_url` 1 hit,grep `from sqlalchemy.engine.url import` 1 hit,无 `from app` import |
| 6 | `_db_url.py` 防御性 assert | grep `拒绝以生产 URL 作为测试 URL` + grep `DATABASE_URL 不包含 database 字段` 各 1 hit |
| 7 | `conftest.py` import | grep `from tests._db_url import derive_test_database_url` 1 hit |
| 8 | `conftest.py` L25 切换 | grep `derive_test_database_url(settings.database_url)` 1 hit,**且**原 `replace("/aipm_db", "/aipm_db_test")` 在 conftest.py 中 grep 0 hit |
| 9 | `test_notifications.py` import | grep `from tests._db_url import derive_test_database_url` 1 hit |
| 10 | `test_notifications.py` L93 切换 | grep `derive_test_database_url(settings.database_url)` 1 hit,**且**原 `.replace("/aipm_db", "/aipm_db_test")` 在 test_notifications.py 中 grep 0 hit |
| 11 | `_clean_notification_settings` fixture | grep `def _clean_notification_settings(monkeypatch)` 1 hit + `autouse=True` 在装饰器位 + 13 个 `monkeypatch.setattr(settings,` 命中 |
| 12 | 13 项 setattr 字段顺序 | 顺序锁定 wechat 5 → dingtalk 5 → smtp 4(grep 输出按行号自然排序 = 字面量顺序) |
| 13 | `.env.example` 4 行兼容别名注释 | grep `# 兼容别名(config.py AliasChoices)` 在 `.env.example` 命中 4 次(WECOM / DINGTALK / LITELLM / MAIL 各 1) |
| 14 | `.env.example` 零删除 | `git diff <feat>^..<feat> -- backend/.env.example \| grep "^-[^-]" \| wc -l` = 0 |
| 15 | `README.md` 最小必填项清单 | grep `最小必填项(否则后端启动会失败)` 在 README.md 命中 1 次 + 5 项 env 名全部在该段出现 |
| 16 | `README.md` 零删除 | `git diff <feat>^..<feat> -- README.md \| grep "^-[^-]" \| wc -l` = 0 |
| 17 | ruff check | `ruff check tests/_db_url.py tests/conftest.py tests/test_notifications.py` All passed |
| 18 | mypy | `mypy tests/_db_url.py tests/conftest.py tests/test_notifications.py` 0 error |
| 19 | pytest 全套 | `pytest -q` 必须 0 failed, ≥178 passed, 2 skipped(从 T-1101 完工基线零回归) |
| 20 | pytest 议题 A 单点 | `pytest -q tests/test_notifications.py::test_notify_unconfigured_channels_skipped -v` 必须 1 passed |
| 21 | pytest 议题 C 单点 | §5 ④ Python 内联验证(3 用例 derive helper)输出 `derive_test_database_url helper PASS` |
| 22 | Worker timestamp 双 commit | feat + chore commit message 均含 `Worker timestamp: [...]` 行 + multi-line body(非极简一行) |

**额外指挥官手工抽查**:
- `docs/dev_tasks.md` Task 2 状态 `[/]` → `[x]`(chore commit 后)。
- `📣 锚点` 段在结尾追加 T-1102 完工时间戳引用块,**不擦除** T-1102 持牌交接单字面量(留作审计)。
- 4 既定 untracked + `.claude/` 保留;`backend/uv.lock` 不进 add 列表。

**全 22 项 PASS** → 验收通过 → Phase 11 第二任 Task 收口。

---

## §9 风险与回滚

### 风险

1. **`backend/tests/__init__.py` 历史是否存在导致 import 路径变化**(中度):若历史无 `__init__.py`,新建后 pytest 解释 tests 为 package,可能引入既有 test 模块 import 路径冲突(虽然 pytest rootdir + `pythonpath` 配置通常容错)。
   - 缓解:Worker 在步骤 1 探针中显式 ls;若新建,跑 pytest 闸门时若出现 `ModuleNotFoundError: tests.*` / `ImportError`,**立即在终端打印 traceback 停手**,**不**尝试改 `pyproject.toml` 或 `pytest.ini`,等待指挥官诊断。
   - **fallback 路径**:若 `from tests._db_url import` 在已有 `__init__.py` 缺失时 import 失败,Worker 可改为 `from _db_url import derive_test_database_url`(相对 backend/ 工作目录 + `pythonpath` 包含 `tests/` 时可工作)。但**优先**先尝试新建 `__init__.py`。

2. **`monkeypatch.setattr(settings, ...)` 在 pydantic v2 `BaseSettings` 上的兼容性**(低度):pydantic v2 `BaseSettings` 实例属性是 `model_fields` 计算后的 Python 属性,`monkeypatch.setattr` 应可直接 setattr。但若 pydantic 用 `Field(frozen=True)` 等保护机制,`setattr` 会抛 `ValidationError`。
   - 缓解:`config.py` 检查无 `frozen=True`(`SettingsConfigDict` 默认非冻结),应可直接 setattr。若 Worker 跑 pytest 闸门时遇到 `ValidationError` 或 `AttributeError` raised by frozen,**立即停手报指挥官**,**不**改 `config.py` 解封 frozen。
   - **fallback 路径**:改用 `monkeypatch.setattr("app.config.settings.wechat_corp_id", "")`(字符串路径形式),pytest monkeypatch 可处理。

3. **`pytest._pytest.MonkeyPatch` 在 module-scope autouse fixture 上的 scope 兼容性**(低度):pytest 默认 `monkeypatch` fixture 是 function scope。`autouse=True` 在 function scope 上每个 test case 都跑一次 setattr/还原循环,**性能成本可忽略**(13 次属性赋值 < 1ms × 8 test = < 10ms,远小于 DB I/O)。
   - 缓解:不必改 scope,function-scope autouse 已经足够。

4. **`.env.example` 注释插入位置精确性**(中度):若 Worker 把注释行插错位置(如插到 `WECHAT_CORP_ID=...` 之后而非之前),语义颠倒。
   - 缓解:§3.4.1 表格中**明确**标注「在该行**之前**插入」+ 复制粘贴字面量,Worker 严禁手敲。

5. **`README.md` 插入位置(L31 之后 / L33 之前)精确性**(中度):若 Worker 把清单插到错误段落(如部署生产段),用户不会读到。
   - 缓解:§3.5.1 用「Step 1 后追加」+ 上下空行隔开,语义清晰。Worker 在改动前可 `grep -n "Step 1\|Step 2" README.md` 复核位置。

### 回滚

- **feat commit 回滚**:`git revert <feat-sha>` —— 6 文件回滚,helper + 测试 + 文档全恢复原状。
- **chore commit 回滚**:`git revert <chore-sha>` —— 回滚 `dev_tasks.md` 状态字符 + 锚点。
- **`backend/tests/__init__.py` 若新建后想撤销**:`git rm backend/tests/__init__.py && git commit`(本任务零依赖该文件,只是 package 化的隐式约定)。
- 零 src 改动,零 alembic 改动,**回滚 0 风险**。

---

## §10 📣 给 Worker (Codex) 的物理交接单

> **指挥官签字时间戳**:`[2026-05-28 17:21:38]`
> **持牌任务**:**T-1102**(Phase 11 **第二任** — 测试隔离 + 配置漂移修复,议题 A + B + C 三合一,**零业务 src 改动**)

- **执行入口**:**必须读完整** `docs/T-1102_spec.md`(本文件 ~620 行,10 章 + 📣 附录)。**必须**在改动前跑前置探针(`git status --short --branch` / `git log -3 --oneline` / `git diff` / `git diff --cached` + `ls backend/tests/__init__.py`),核验 HEAD = `chore(spec): T-1102 契约起草` commit 之后,工作树干净(仅 `dev_tasks.md` Task 2 已被指挥官加锁 `[/]`),4 既定 untracked + `.claude/` 保留。

- **核心动作**(2 commit / 5-6 文件 = `_db_url.py` 新建 + `conftest.py` + `test_notifications.py` + `.env.example` + `README.md` + dev_tasks.md + 可能新建 `__init__.py`):

  **Commit 1 (fix/feat)** — `fix(tests): T-1102 harden test isolation and config drift — derive_test_database_url helper + notification settings monkeypatch + .env.example aliases + README minimum env checklist`:

  **议题 C 主修复**(优先做,后两步依赖 helper 存在):
  1. **新建** `backend/tests/_db_url.py`(§3.1 完整字面量复制粘贴,~50 行)。
  2. **(条件)** 若 `ls backend/tests/__init__.py` 返回 not found,**新建空文件** `backend/tests/__init__.py`(0 字节);已存在则跳过。
  3. **改** `backend/tests/conftest.py`:
     - 在 `from app.main import app`(L21)之后加空行 + `from tests._db_url import derive_test_database_url`(§3.2.1)。
     - **替换** L25 整行为 `TEST_DATABASE_URL = os.getenv("DATABASE_URL_TEST") or derive_test_database_url(settings.database_url)`(中文议题 C 解释注释 2 行追加在 L25 注释之前,见 §3.2.1 完整字面量)。
  4. **改** `backend/tests/test_notifications.py`:
     - 在 L33(`from app.services.notification_service import notify, render_template`)之后插入 `from tests._db_url import derive_test_database_url`(§3.3.1)。
     - **替换** L93 整行为 `TEST_DATABASE_URL = derive_test_database_url(settings.database_url)`(§3.3.1)。

  **议题 A 主修复**:
  5. **改** `backend/tests/test_notifications.py`:在 L107(`isolated_db` fixture 结束)之后 / L110(`@pytest.mark.asyncio`)之前,插入 `_clean_notification_settings(monkeypatch)` autouse fixture(§3.3.2 完整字面量,13 项 setattr 顺序锁定)。

  **议题 B 主修复**:
  6. **改** `backend/.env.example`:在 4 处章节头(WECHAT L24 之前 / DINGTALK L45 之前 / NEW_API L56 之前 / SMTP L92 之前)**纯插入** 1 行 `# 兼容别名(config.py AliasChoices):XXX`(§3.4.1 字面量逐条复制粘贴)。**严禁**改 L66 OSS(已有兼容别名注释)。
  7. **改** `README.md`:在 L31 `# 编辑 .env，填写企微、NewApi、数据库连接等配置` 之后 / L33 `# ── Step 2: ...` 之前,**纯插入** 7 行最小必填项清单 + 上下各 1 空行(§3.5.1 字面量)。

  **Commit 2 (chore)** — `chore(progress): close T-1102 — Phase 11 测试隔离 + 配置漂移修复完工`:
  8. **改** `docs/dev_tasks.md`:
     - L230 Task 2 `[/]` → `[x]`,标题改为 `**Task 2 (T-1102): 测试隔离污染 + 配置漂移仓库层面修复(议题 A + B + C 三合一)** — Done by Codex `[YYYY-MM-DD HH:MM:SS]``。
     - **保留** L231-238 子 bullet 全部不动(议题 A/B/C 描述本就是 T-1102 范围)。
     - 在 📣 锚点段**末尾**追加(**不擦除** T-1102 持牌字面量):
       ```markdown
       > **更新时间戳(T-1102 完工)**: `[YYYY-MM-DD HH:MM:SS]`
       > **当前持牌任务**: 无(T-1102 已 `[x]`,议题 A/B/C 三合一收口;等待指挥官二次验收)。**绝对不要**自启 T-1103。**绝对不要** `git push`。
       ```

- **严禁项**(违反立即驳回,详见 §6 完整 25 项):
  - **严禁**改 `backend/app/` 任何文件(包括 `config.py` —— pydantic 必填 + AliasChoices 已生效,不叠加自定义 validator)。
  - **严禁**改 `backend/alembic/` 任何 migration。
  - **严禁**改 `frontend/` 任何文件。
  - **严禁**改 `DEPLOY.md`(本任务面向本地开发,不重写生产部署清单)。
  - **严禁**改 `backend/.env`(个人本机配置)。
  - **严禁**改 `backend/tests/` 上述白名单 3 文件 + `_db_url.py` + `__init__.py` 之外的任何 test。
  - **严禁**给 `_clean_notification_settings` 加超范围 setattr(`new_api_*` / `oss_*` / `jwt_*` 等非通知通道字段不允许)。
  - **严禁**给 `notify_service` 加防御性代码(议题 A 是测试问题,不是 service bug)。
  - **严禁**在 `.env.example` / `README.md` 中**删除**任何现有行(只能纯插入)。
  - **严禁** `git push`(留给指挥官决策推送时机)。
  - **严禁**自启 T-1103 / Phase 11 后续任务。
  - **严禁** revert `8459a5b` / `b5e77c3` / `1c67bd4` / `19ac08e` / `8d69ca8` 任何已落地 commit。
  - **严禁**在 feat / chore commit 之外打额外提交(`chore(lock)` 已由指挥官代办)。
  - **严禁**在两条 commit message 中遗漏 `Worker timestamp:` 行 或 写极简一行 commit message。

- **闸门**(全绿才提交,详见 §5):
  ```bash
  cd backend
  .venv/bin/ruff check tests/_db_url.py tests/conftest.py tests/test_notifications.py
  .venv/bin/mypy tests/_db_url.py tests/conftest.py tests/test_notifications.py
  .venv/bin/pytest -q   # 0 failed, ≥178 passed, 2 skipped
  .venv/bin/pytest -q tests/test_notifications.py::test_notify_unconfigured_channels_skipped -v   # 1 passed
  .venv/bin/alembic check   # No new upgrade operations

  # 议题 C 单点(derive helper 3 用例)
  .venv/bin/python -c "
  from tests._db_url import derive_test_database_url
  assert derive_test_database_url('postgresql+asyncpg://u:p@h:5432/aipm_db').endswith('/aipm_db_test')
  assert derive_test_database_url('postgresql+asyncpg://u:p@h:5432/qiaocai').endswith('/qiaocai_test')
  print('derive_test_database_url helper PASS')
  "
  ```

  改动面校验:
  ```bash
  cd ..
  git diff <feat-sha>^..<feat-sha> -- backend/app/ backend/alembic/ frontend/ DEPLOY.md backend/.env   # 必须空
  git diff <feat-sha>^..<feat-sha> --name-only   # 严格 5-6 文件,无其他
  ```

- **完工提交序列**(2 commit,顺序锁定):
  1. `fix(tests): T-1102 harden test isolation and config drift — derive_test_database_url helper + notification settings monkeypatch + .env.example aliases + README minimum env checklist` —— **5-6 文件**(根据 `__init__.py` 是否新建)。
  2. `chore(progress): close T-1102 — Phase 11 测试隔离 + 配置漂移修复完工` —— **1 文件**(`dev_tasks.md`)。

  两条 commit message 都**必须**包含 multi-line body(对比 T-1005/T-1007/T-1008 风格)+ 末尾 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 行。

- **时间戳纪律**:所有 commit message 末尾、终端汇报、`dev_tasks.md` 段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

- **完工后**:立即停手汇报「T-1102 完工,议题 A/B/C 三合一收口,pytest 1 failed → 0 failed,178 passed + 2 skipped。等待指挥官二次验收 + Phase 11 后续 task 起草」。**绝对不要**自启 T-1103。**绝对不要** `git push`。
