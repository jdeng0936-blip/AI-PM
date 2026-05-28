# T-1103 实施契约:测试隔离彻底化 + T-1102 议题 C 残留 11 处统一收口

> **指挥官签字时间戳**:`[2026-05-28 18:25:08]`
> **持牌任务**:Phase 11 **第三任** — 测试隔离 fixture 全局化(议题 A)+ 双处之外的 11 处 `.replace` 硬编码批量切换(议题 B)
> **触发来源**:
> - **议题 A 触发**:T-1102 议题 A 只修了 `test_notifications.py` 一个点,**其余 10 个引用 settings 的 test file 仍依赖跑测试者本机 `.env`**(`test_asr.py / test_attachments.py / test_okr.py / ...`)。需要"一劳永逸"全局化。
> - **议题 B 触发**(🚨 **关键发现**):T-1102 议题 C spec 起草时**勘察盲点** — 只修了 `conftest.py:25` + `test_notifications.py:93` 两处 `.replace("/aipm_db", "/aipm_db_test")`,T-1103 指挥官全仓 grep 发现**还有 11 处其他 test file 同样硬编码**(全列在 §1)。`drop_all` 红线风险未根除,必须批量收口。
> **范围**:**纯 test 代码 + helper**,**零业务 src 改动**(`backend/app/` + `backend/alembic/` + `frontend/` + `DEPLOY.md` + `backend/.env` 全冻结)。

---

## §1 任务概述

### 议题 A — 测试隔离 fixture 全局化(从 test_notifications 推广到 conftest)

T-1102 议题 A 仅在 `test_notifications.py:111` 加了 `_clean_notification_settings(monkeypatch)` autouse fixture,**只覆盖该单一文件**。其他 test file 中**任何引用 settings 的 service 调用**(notify / asr / oss / email / sentry / erp_webhook),都仍依赖跑测试者本机 `.env` 状态。

**勘察证据**(T-1103 指挥官 `[2026-05-28 17:50]` 全仓 grep):

| Test 文件 | 引用 settings 数 | 已有 monkeypatch | env 敏感字段命中 | 风险等级 |
|----------|-----------------|----------------|---------------|---------|
| test_notifications.py | 2 | 15(T-1102 已修)| 13 | ✅ 已修 |
| test_asr.py | 7 | 34 | 21 | 中(test 内已 setattr 各 case,但缺 baseline 清空)|
| test_attachments.py | 2 | 7 | 11 | 中(oss / local_upload_dir)|
| test_okr.py | 2 | 7 | 1 | 低 |
| test_chat_tools.py | 2 | 1 | 0 | 低 |
| test_retro.py | 2 | 15 | 0 | 低 |
| test_capacity.py | 2 | 30 | 0 | 低 |
| test_kpi_phase9.py | 2 | 0 | 0 | 中(2 settings 引用未 monkeypatch,可能依赖默认值)|
| test_phase10_dept_group.py | 2 | 0 | 0 | 中 |
| test_analytics.py | 2 | 0 | 0 | 中 |
| test_me_deletions.py | 2 | 0 | 0 | 中 |
| test_daily_report_relations.py | 2 | 0 | 0 | 中 |
| test_sprints.py | 2 | 0 | 0 | 中 |

**根本修复**:在 `backend/tests/conftest.py` 加全局 autouse=True fixture `_isolation_external_settings`,引用新建 helper `backend/tests/_isolation.py::clean_external_settings(monkeypatch)`,把**所有外部敏感 settings**(wechat / dingtalk / smtp / asr / oss / new_api / sentry / erp_webhook)统一清空。让**任何 test**(包括未来新写的)都自动享受 isolation,**无需 opt-in**。

**为何不破坏现有 test**:`monkeypatch.setattr` 是函数 scope,fixture autouse 在 test body 之前 setattr 空值,test 内若需要测"已配置时的真实分支"(如 `test_asr.py::test_xunfei_configured_when_provider_is_xunfei`),test 内自己再 setattr 真值,**later setattr wins**(monkeypatch 不是 stack,是顺序覆盖)。已 verified 不影响 test_asr.py 等显式 setattr 的 33 个 case。

### 议题 B — T-1102 议题 C 残留 11 处 `.replace` 硬编码统一收口(🚨)

T-1102 议题 C spec 起草时**勘察盲点**:只确认 `conftest.py:25` + `test_notifications.py:93` 双处硬编码,实际**还有 11 处分散在其他 test file**,**全部继承同源红线风险**。

**T-1103 指挥官全仓 `grep -rn 'replace.*aipm_db.*aipm_db_test' backend/tests/`** 完整命中清单(11 行,逐一收口):

```
backend/tests/test_okr.py:33
backend/tests/test_daily_report_relations.py:34
backend/tests/test_analytics.py:23
backend/tests/test_sprints.py:42
backend/tests/test_retro.py:34
backend/tests/test_capacity.py:43
backend/tests/test_kpi_phase9.py:31
backend/tests/test_phase10_dept_group.py:44
backend/tests/test_attachments.py:32
backend/tests/test_chat_tools.py:27
backend/tests/test_me_deletions.py:21
```

每处**字面量统一**:`TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")`(11 处完全一样,可以 sed-able,但 spec 要求 Read + 精确 Edit 每处,**严禁** sed 一刀切)。

**根本修复**:每处 2 行变更 — ① import `from tests._db_url import derive_test_database_url`(顺序符合现有 import 区,通常 `from app.config` 之后)+ ② 替换 `TEST_DATABASE_URL = derive_test_database_url(settings.database_url)`(单行替换)。

**红线根除证据**:T-1102 完工后只有 2/13 处切换;T-1103 完工后 13/13 全部切换,**全仓零 `.replace("/aipm_db", "/aipm_db_test")` 硬编码**(`_db_url.py:5` 注释内的字面量不算 — 它是 helper docstring 解释)。

---

## §2 文件范围锁定(严格 14 文件,白名单)

```
+ backend/tests/_isolation.py              # 新建,~80 行,clean_external_settings(monkeypatch) helper
+ backend/tests/conftest.py                # 加 import + 加全局 autouse=True _isolation_external_settings fixture
+ backend/tests/test_notifications.py      # 移除 _clean_notification_settings fixture(L111-134 共 24 行,由 conftest.py autouse 替代)
+ backend/tests/_db_url.py                 # 更新 docstring L5 从「双处」改为「双处+T-1103 扩展为全仓 13 处」 (1 行注释更新,非功能改动)

# 议题 B 11 处批量切换
+ backend/tests/test_okr.py                # +1 import + 1 行 .replace → derive_test_database_url
+ backend/tests/test_daily_report_relations.py
+ backend/tests/test_analytics.py
+ backend/tests/test_sprints.py
+ backend/tests/test_retro.py
+ backend/tests/test_capacity.py
+ backend/tests/test_kpi_phase9.py
+ backend/tests/test_phase10_dept_group.py
+ backend/tests/test_attachments.py
+ backend/tests/test_chat_tools.py
+ backend/tests/test_me_deletions.py

+ docs/dev_tasks.md                        # Task 3 (T-1103) `[ ]` → `[/]`(本契约 commit 加锁)+ 📣 锚点重写
```

**严禁清单**(改动一律驳回):

- ❌ 改 `backend/app/` 任何文件(包括 `config.py` / `services/*` / `routers/*` / `models/*`)
- ❌ 改 `backend/alembic/` 任何 migration
- ❌ 改 `frontend/` 任何文件
- ❌ 改 `backend/tests/` 白名单 14 文件 + `_db_url.py` 之外的任何 test(`test_distributed_lock.py` / `test_e2e_ipd.py` / `test_export_phase8.py` / `test_models_init.py` / `test_simulate_reports.py` / `test_deletion_cleanup.py` / `test_deletion_history.py` — 都不在白名单内,**因为它们没有 `.replace` 硬编码**)
- ❌ 改任何 `docs/T-1XXX_spec.md` 历史契约
- ❌ 改 `DEPLOY.md` / `README.md` / `backend/.env` / `backend/.env.example`(T-1102 已完工的配置漂移议题不重做)
- ❌ 动 4 既定 untracked 文件(`.cursorrules` / `CLAUDE.md` / `CONVENTIONS.md` / `backend/uv.lock`)
- ❌ 动 `.gitignore` / `.claude/` 项目级 ECC symlinks
- ❌ 自动 `git push`
- ❌ 自启 T-1104 / Phase 11 后续任务
- ❌ 改 `notify_service` / `oss_service` / `xunfei_asr` / `gemini_asr` / 任何业务逻辑(议题 A 是**测试**自治问题,不是 service bug)
- ❌ 把 11 处替换为不同字面量(必须**统一** `derive_test_database_url(settings.database_url)`)
- ❌ 用 sed 批量 replace(必须 Read + 精确 Edit 每处,逐文件审计)

---

## §3 详细文件改动

### §3.1 新建 `backend/tests/_isolation.py`(议题 A 主修复)

**完整文件字面量**(~80 行,逐字符锁定):

```python
"""
tests/_isolation.py — 测试隔离 helper:统一清空所有外部敏感 settings

议题:T-1103 议题 A — T-1102 议题 A 在 test_notifications.py 单文件加了
`_clean_notification_settings(monkeypatch)` autouse fixture,只覆盖通知通道
13 项 settings。但**其他 test file 中任何引用 settings 的 service 调用**
(notify / asr / oss / email / sentry / erp_webhook)仍依赖跑测试者本机 .env
状态。本 helper 抽出统一清空逻辑,供 `conftest.py` 全局 autouse=True 调用,
让任何 test(包括未来新写的)都自动享受 isolation。

为何不破坏现有 test:monkeypatch.setattr 是函数 scope,fixture autouse 在 test
body 之前 setattr 空值,test 内若需要测「已配置时的真实分支」(如
test_asr.py::test_xunfei_configured_when_provider_is_xunfei),test 内自己再
setattr 真值,later setattr wins(monkeypatch 顺序覆盖而非 stack)。
"""

from __future__ import annotations

from typing import Any


# 锁定 28 项外部敏感字段(覆盖 wechat / dingtalk / smtp / asr / oss / new_api /
# sentry / erp_webhook 8 个外部依赖类别)。新增字段时,**只在此 list 追加**,
# 严禁在 conftest.py / 单元 test 中分散维护别名。
_EXTERNAL_SETTINGS_FIELDS: tuple[str, ...] = (
    # 企业微信(6 项)
    "wechat_corp_id",
    "wechat_corp_secret",
    "wechat_agent_id",
    "wechat_token",
    "wechat_encoding_aes_key",
    "wechat_bot_webhook",
    # 钉钉(5 项)
    "dingtalk_bot_webhook",
    "dingtalk_bot_secret",
    "dingtalk_app_key",
    "dingtalk_app_secret",
    "dingtalk_agent_id",
    # 邮件 SMTP(4 项)
    "smtp_server",
    "smtp_user",
    "smtp_password",
    "smtp_from_email",
    # 大模型网关(2 项)
    "new_api_base_url",
    "new_api_key",
    # 讯飞 ASR(3 项)
    "xunfei_app_id",
    "xunfei_api_key",
    "xunfei_api_secret",
    # OSS 对象存储(5 项)
    "oss_endpoint",
    "oss_bucket",
    "oss_access_key",
    "oss_secret_key",
    "oss_public_url_base",
    # ERP webhook(1 项)
    "erp_webhook_secret",
    # Sentry(2 项)
    "sentry_dsn",
    "sentry_environment",
)


def clean_external_settings(monkeypatch: Any) -> None:
    """
    把所有外部敏感 settings 字段 setattr 为空字符串,让 service 层的
    `is_configured()` 等检查走「未配置」分支,test 走干净基线。

    test 内若需要测「已配置」分支,直接在 test body 中 monkeypatch.setattr
    覆盖即可(later setattr wins)。

    Args:
        monkeypatch: pytest 的 monkeypatch fixture 实例(MonkeyPatch 类型),
            函数 scope,test 结束自动还原。

    Notes:
        - 不修改 `database_url` / `redis_url` / `jwt_secret_key`(测试核心依赖,
          不应被清空,否则 conftest.py setup_test_db / app.config 自身解析失败)。
        - `aipm_env` / `enable_dev_*` 等运行环境开关也不清空(测试基础设施依赖)。
        - 使用 `raising=False` 防御未来字段重命名,fixture 仍 graceful 通过。
    """
    # 延迟 import 避免 conftest.py 启动时循环依赖
    from app.config import settings

    for field in _EXTERNAL_SETTINGS_FIELDS:
        monkeypatch.setattr(settings, field, "", raising=False)
```

**字面量注意点**:
- `from __future__ import annotations` 必带。
- `_EXTERNAL_SETTINGS_FIELDS` **28 项**字段(wechat 6 + dingtalk 5 + smtp 4 + new_api 2 + xunfei 3 + oss 5 + erp 1 + sentry 2 = 28),覆盖 8 个外部依赖类别。**顺序锁定**(逐类别注释)。
- 函数签名 `monkeypatch: Any`(避免 `from _pytest.monkeypatch import MonkeyPatch` 引入 internal API 依赖)。
- 延迟 `from app.config import settings` 防止循环依赖(`conftest.py` 启动时 import 顺序)。
- docstring 中 `is_configured()` / `monkeypatch.setattr` 字面量保留(对齐项目其他 helper 风格)。
- 与 `_db_url.py` 一样,**纯函数**,**不引入任何业务依赖**(除了延迟 import `app.config.settings`)。

### §3.2 改 `backend/tests/conftest.py`(议题 A 主调用)

#### §3.2.1 加 autouse fixture(单点插入)

**位置**:`conftest.py` 现有的 `db_session`(L74)/ `client`(L85)之前 / `setup_test_db`(L44)之后。

**当前 L70-78 上下文**:

```python
    await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    每个测试用例独立的数据库 session，自动回滚。
    """
```

**改后**:在 `await test_engine.dispose()` 之后 + `@pytest_asyncio.fixture\nasync def db_session` 之前,**插入** import 和 fixture:

1. 文件顶部 import 区(`from tests._db_url import derive_test_database_url` 之后)插入:
   ```python
   from tests._isolation import clean_external_settings
   ```
2. 在 `setup_test_db` fixture 体结束(`await test_engine.dispose()` 之后)+ `db_session` fixture 之前,插入:

```python


@pytest.fixture(autouse=True)
def _isolation_external_settings(monkeypatch):
    """
    T-1103 议题 A:全局测试隔离 — 清空所有外部敏感 settings(wechat / dingtalk /
    smtp / asr / oss / new_api / sentry / erp_webhook),让任何 test 不依赖
    跑测试者本机 .env 状态。

    autouse=True 让所有 test case 默认享受 isolation。test 内若需要测「已配置」
    分支,自行 monkeypatch.setattr 覆盖(later setattr wins)。
    """
    clean_external_settings(monkeypatch)
```

**字面量注意点**:
- `@pytest.fixture(autouse=True)`(**不是** `@pytest_asyncio.fixture`,本 fixture 同步,不依赖 event loop)。
- function scope(默认),与 `monkeypatch` 同 scope。
- fixture name `_isolation_external_settings`(下划线前缀表示内部 fixture,不希望 test 主动 request)。
- 调用 helper `clean_external_settings(monkeypatch)`,**不在 conftest.py 内 inline 28 setattr**(单一职责)。

### §3.3 改 `backend/tests/test_notifications.py`(议题 A 去重)

#### §3.3.1 移除 `_clean_notification_settings` fixture(L111-134)

**当前 L109-135 上下文**:

```python
    await engine.dispose()


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


@pytest.mark.asyncio
async def test_notify_in_app_only(isolated_db):
```

**改后**:**整段删除** L111-134(`@pytest.fixture(autouse=True)` 行 + def + docstring + 13 setattr 共 **24 行**),保留 L109(`await engine.dispose()`)+ L110(空行)+ L135(空行)+ L136(`@pytest.mark.asyncio`)。

**理由**:`conftest.py` 全局 autouse fixture(§3.2.1)已经在所有 test 入口前清空 13 项通知 settings(+15 项其他外部 settings = 28 项)。`test_notifications.py` 内的 `_clean_notification_settings` 是**重复 fixture**(同 scope + 同 monkeypatch + 子集字段),保留=死代码,清理 = 单一真理源。

**注**:`settings` import(L24 `from app.config import settings`)**保留不动**(其他 test fixture / setup 可能用,不去清理超范围)。

### §3.4 更新 `backend/tests/_db_url.py` docstring(议题 B 注释同步,1 行)

**当前 L4-7**:

```python
议题:T-1102 议题 C — `conftest.py:25` 与 `test_notifications.py:93` 双处硬编码
`settings.database_url.replace("/aipm_db", "/aipm_db_test")`,在 DB 名不是
`aipm_db` 时(如 `qiaocai` / 用户自定义),replace 不命中,TEST_DATABASE_URL
落到生产库,`Base.metadata.drop_all` 会清生产表 —— 红线风险。
```

**改后**(替换 L4-7):

```python
议题:T-1102 议题 C(双处)+ T-1103 议题 B(扩展为全仓 13 处)— `conftest.py:25` /
`test_notifications.py:93` / 11 处其他 test file 同样硬编码
`settings.database_url.replace("/aipm_db", "/aipm_db_test")`,在 DB 名不是
`aipm_db` 时(如 `qiaocai` / 用户自定义),replace 不命中,TEST_DATABASE_URL
落到生产库,`Base.metadata.drop_all` 会清生产表 —— 红线风险。
```

**字面量改动量**:4 行替换为 5 行,纯注释同步,**零功能影响**(helper 函数体本身不动)。

### §3.5 改 11 处 test file(议题 B 主修复,逐文件统一切换)

**通用改动模式**(11 文件完全相同):

1. **加 import**:在文件 import 区(通常 `from app.config import settings` 之后 / 第一个 `def test_*` 或 fixture 之前)**插入** 一行:
   ```python
   from tests._db_url import derive_test_database_url
   ```

2. **替换 TEST_DATABASE_URL 行**(每文件 1 处):
   - **删除** `TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")`
   - **插入** `TEST_DATABASE_URL = derive_test_database_url(settings.database_url)`

**逐文件锁定位置表**(Worker 必须**逐文件 Read + 精确 Edit**,**严禁** sed 批量 replace):

| # | 文件 | TEST_DATABASE_URL 当前所在行 | 期望切换后字面量 |
|---|------|--------------------------|----------------|
| 1 | `backend/tests/test_okr.py` | L33 | `TEST_DATABASE_URL = derive_test_database_url(settings.database_url)` |
| 2 | `backend/tests/test_daily_report_relations.py` | L34 | 同上 |
| 3 | `backend/tests/test_analytics.py` | L23 | 同上 |
| 4 | `backend/tests/test_sprints.py` | L42 | 同上 |
| 5 | `backend/tests/test_retro.py` | L34 | 同上 |
| 6 | `backend/tests/test_capacity.py` | L43 | 同上 |
| 7 | `backend/tests/test_kpi_phase9.py` | L31 | 同上 |
| 8 | `backend/tests/test_phase10_dept_group.py` | L44 | 同上 |
| 9 | `backend/tests/test_attachments.py` | L32 | 同上 |
| 10 | `backend/tests/test_chat_tools.py` | L27 | 同上 |
| 11 | `backend/tests/test_me_deletions.py` | L21 | 同上 |

**字面量注意点**:
- import 位置:每文件 Worker 应 `grep -n "from app.config import settings" backend/tests/test_XXX.py` 定位,在该行 **之后**插入 `from tests._db_url import derive_test_database_url`(无需空行)。若该 test file 没 `from app.config import settings` import(不太可能),Worker 应 stop and ask 指挥官。
- 替换字面量**完全统一**(`derive_test_database_url(settings.database_url)`),11 个文件**逐字符相同**,但**严禁** sed 一刀切 — Worker 必须 Read 每文件确认上下文(import 区已存在 from-imports / 是否需要排序),逐个 Edit。

### §3.6 改 `docs/dev_tasks.md`(本契约 commit 一起 add)

#### §3.6.1 加 Phase 11 Task 3 (T-1103) entry

**位置**:`docs/dev_tasks.md` Phase 11「## 任务看板」段下,Task 2 (T-1102) 完工 entry 之后(目前是 L230 起 + L241 末 bullet),**在 `---` 分隔符之前**插入 Task 3 entry。

**字面量插入块**(锁定):

```markdown
- [/] **Task 3 (T-1103): 测试隔离 fixture 全局化 + T-1102 议题 C 残留 11 处 `.replace` 硬编码收口** — In Progress by Codex `[2026-05-28 18:25:08]`(指挥官契约起草中)
  - **议题 A — 测试隔离 fixture 全局化**:T-1102 议题 A 只修了 `test_notifications.py` 一个文件,其余 10 个引用 settings 的 test file 仍依赖跑测试者本机 `.env`。修复路径:新建 `backend/tests/_isolation.py`(~80 行,`clean_external_settings(monkeypatch)` helper,清空 28 项外部敏感 settings = wechat 6 + dingtalk 5 + smtp 4 + new_api 2 + xunfei 3 + oss 5 + erp 1 + sentry 2),在 `conftest.py` 加全局 autouse=True `_isolation_external_settings` fixture 调用 helper。**移除** `test_notifications.py:111-134` `_clean_notification_settings` fixture(T-1102 版本),由 conftest.py 全局 fixture 替代(去重,单一真理源)。
  - **议题 B — T-1102 议题 C 残留 11 处统一收口**(🚨 T-1102 spec 起草盲点):全仓 grep `replace.*aipm_db.*aipm_db_test` 命中 **13 处**,T-1102 只修了 2 处(conftest.py + test_notifications.py),其余 11 处(test_okr.py / test_daily_report_relations.py / test_analytics.py / test_sprints.py / test_retro.py / test_capacity.py / test_kpi_phase9.py / test_phase10_dept_group.py / test_attachments.py / test_chat_tools.py / test_me_deletions.py)继承同源**红线风险**(DB 名非 `aipm_db` 时 `drop_all` 清生产库)。修复路径:每文件 2 行变更 — ① import `from tests._db_url import derive_test_database_url` + ② 替换 `.replace(...)` 为 `derive_test_database_url(settings.database_url)`,**逐文件 Read + 精确 Edit**,**严禁** sed 一刀切。同步更新 `_db_url.py` docstring L4-7 从「双处」改为「双处 + T-1103 扩展为全仓 13 处」。
  - **不**改 `backend/app/`、`backend/alembic/`、`frontend/`、`DEPLOY.md`、`backend/.env`、`backend/.env.example`、`README.md` 任何文件(T-1102 已完工的配置漂移议题不重做)。
  - **完整执行契约见 `docs/T-1103_spec.md`**(必读,~600 行 10 章 + 📣 附录)。
```

#### §3.6.2 重写 L246-247 「📣 恢复执行指令」锚点段(整段替换为 T-1103 持牌发牌)

**当前 L244-247**(T-1102 完工终态):

```markdown
## 📣 恢复执行指令

> **更新时间戳(T-1102 完工)**: `[2026-05-28 18:05:00]`
> **当前持牌任务**: 无(T-1102 已 `[x]`,议题 A/B/C 三合一收口;等待指挥官二次验收)。**绝对不要**自启 T-1103。**绝对不要** `git push`。
```

**整体替换为**(字面量,逐字符锁定,见 **§10 物理交接单 详细字面量**)。

---

## §4 执行步骤(逐步可审计)

1. **前置探针**(强制):
   ```bash
   git status --short --branch
   git log -3 --oneline
   git diff
   git diff --cached
   ```
   必须确认:HEAD = `<指挥官 chore(spec): T-1103 契约起草 commit 短 sha>`(本契约 commit 落地后),工作树 clean,4 既定 untracked + `.claude/` 保留。

2. **加锁已由指挥官代办**:`docs/dev_tasks.md` 已经被本契约 commit 改为 `[/] In Progress by Codex`,Worker **不必再打 `chore(lock)` commit**,**直接进入步骤 3**。

3. **执行文件改动**(顺序锁定):

   **议题 A 主修复**(优先做,后续 conftest.py 依赖 helper 存在):
   1. **新建** `backend/tests/_isolation.py`(§3.1 完整字面量复制粘贴,~80 行,**28 项**字段顺序锁定)。
   2. **改** `backend/tests/conftest.py`:
      - 在 `from tests._db_url import derive_test_database_url`(T-1102 已加)之后插入 `from tests._isolation import clean_external_settings`。
      - 在 `setup_test_db` fixture 体结束之后 / `db_session` fixture 之前,插入 `_isolation_external_settings(monkeypatch)` autouse fixture(§3.2.1 完整字面量)。
   3. **改** `backend/tests/test_notifications.py`:**整段删除** L111-134 共 24 行 `_clean_notification_settings` fixture(§3.3.1)。

   **议题 B 主修复**:
   4. **改** `backend/tests/_db_url.py`:更新 L4-7 docstring 4 行 → 5 行(§3.4 字面量)。
   5. **改** 11 处 test file(§3.5 表 #1~#11),每文件 2 行变更:
      - 加 import `from tests._db_url import derive_test_database_url`(在 `from app.config import settings` 之后)。
      - 替换 `TEST_DATABASE_URL = settings.database_url.replace(...)` 为 `TEST_DATABASE_URL = derive_test_database_url(settings.database_url)`。

4. **闸门**(全绿才提交):
   ```bash
   cd backend
   .venv/bin/ruff check tests/
   .venv/bin/mypy tests/_isolation.py tests/conftest.py
   .venv/bin/pytest -q                       # 必须 178 passed, 2 skipped(从 T-1102 完工基线零回归)
   .venv/bin/alembic check                   # 跳过(已知 local DB drift)
   ```

5. **改动面校验**:
   ```bash
   cd ..
   # 严格 14 文件(13 test + 1 dev_tasks)
   git diff <feat-sha>^..<feat-sha> --name-only

   # 零 src 闸门
   git diff <feat-sha>^..<feat-sha> -- backend/app/ backend/alembic/ frontend/ DEPLOY.md README.md backend/.env backend/.env.example   # 必须空

   # 议题 B 全仓零残留闸门
   grep -rn 'replace.*aipm_db.*aipm_db_test' backend/tests/ --include='*.py' | grep -v '_db_url.py'   # 必须 0 hit
   ```

6. **提交 feat commit**(单一原子,13 文件):
   ```bash
   git add backend/tests/_isolation.py backend/tests/conftest.py backend/tests/test_notifications.py backend/tests/_db_url.py \
           backend/tests/test_okr.py backend/tests/test_daily_report_relations.py backend/tests/test_analytics.py \
           backend/tests/test_sprints.py backend/tests/test_retro.py backend/tests/test_capacity.py \
           backend/tests/test_kpi_phase9.py backend/tests/test_phase10_dept_group.py backend/tests/test_attachments.py \
           backend/tests/test_chat_tools.py backend/tests/test_me_deletions.py
   git commit -m "fix(tests): T-1103 testsuite-wide isolation hardening — global _isolation_external_settings autouse fixture + 11 derive_test_database_url cutovers

   议题 A — 测试隔离 fixture 全局化:
   - 新建 backend/tests/_isolation.py(~80 行)抽 clean_external_settings(monkeypatch) helper,
     锁定 28 项外部敏感 settings 字段(wechat 6 + dingtalk 5 + smtp 4 + new_api 2 + xunfei 3
     + oss 5 + erp 1 + sentry 2),供 conftest.py 全局 autouse 调用。
   - conftest.py 加 _isolation_external_settings(monkeypatch) autouse=True fixture,
     在 setup_test_db 之后 / db_session 之前,全 test 默认享受 isolation。
   - 移除 test_notifications.py:111-134 _clean_notification_settings fixture(T-1102
     版本),由 conftest.py 全局 fixture 替代,单一真理源。

   议题 B — T-1102 议题 C 残留 11 处 .replace 硬编码统一收口:
   - 全仓 grep 命中 13 处 .replace('/aipm_db', '/aipm_db_test'),T-1102 只修 2 处。
   - 11 处其他 test file 逐个切换为 derive_test_database_url(settings.database_url):
     test_okr.py / test_daily_report_relations.py / test_analytics.py / test_sprints.py /
     test_retro.py / test_capacity.py / test_kpi_phase9.py / test_phase10_dept_group.py /
     test_attachments.py / test_chat_tools.py / test_me_deletions.py。
   - 红线根除证据:grep -rn 'replace.*aipm_db' backend/tests/ --include='*.py' 
     仅 _db_url.py docstring 1 hit(注释,非功能)。

   零 backend/app 改动 / 零 alembic 改动 / 零 frontend 改动 / 零 backend/.env / 零 config 漂移议题。

   Worker timestamp: [YYYY-MM-DD HH:MM:SS]"
   ```

7. **提交 chore(progress) commit**(改 `dev_tasks.md`):
   ```bash
   # docs/dev_tasks.md:
   #   Task 3 (T-1103) [/] → [x] + Done by Codex 时间戳
   #   📣 锚点段重写为 T-1103 完工终态
   git add docs/dev_tasks.md
   git commit -m "chore(progress): close T-1103 — Phase 11 测试隔离全局化 + 议题 C 残留 11 处收口

   - Task 3 (T-1103) [/] → [x]
   - 议题 A:28 项外部 settings 全局 autouse fixture,_clean_notification_settings 去重
   - 议题 B:11 处 .replace 硬编码全部切换为 derive_test_database_url,全仓零残留
   - 改动严格 14 文件(13 test + 1 dev_tasks),零 src / 零 alembic / 零 frontend

   pytest -q: 178 passed, 2 skipped(从 T-1102 完工基线零回归)

   Worker timestamp: [YYYY-MM-DD HH:MM:SS]"
   ```

8. **完工汇报**(终端打印,**不要** `git push`):
   ```
   [YYYY-MM-DD HH:MM:SS] T-1103 完工,议题 A 全局 fixture + 议题 B 11 处统一收口,pytest 178 passed + 2 skipped 零回归。等待指挥官二次验收。
   ```

---

## §5 闸门(Worker 提交前必跑)

```bash
cd backend

# ① ruff / mypy 闸门
.venv/bin/ruff check tests/                                              # All passed
.venv/bin/mypy tests/_isolation.py tests/conftest.py                     # 0 error

# ② pytest 全套闸门(关键)
.venv/bin/pytest -q                                                       # 0 failed, 178 passed, 2 skipped(从 T-1102 基线零回归)

# ③ alembic check 跳过(T-1101 已知 local DB drift,Supervisor 签字)

# ④ 议题 B 全仓零残留闸门(关键)
cd ..
grep -rn 'replace.*aipm_db.*aipm_db_test' backend/tests/ --include='*.py' | grep -v '_db_url.py'
# 必须 0 hit(_db_url.py docstring 内的字面量不算)

# ⑤ 议题 A fixture 单点抽样(test_asr 等仍能 setattr 真值,因 monkeypatch 顺序覆盖)
.venv/bin/pytest -q tests/test_asr.py -v                                  # 全部 passed(test_asr 33 case 验证 monkeypatch later wins)
.venv/bin/pytest -q tests/test_notifications.py -v                        # 全部 passed(_clean_notification_settings 去重后仍 isolated)
```

**改动面校验**:

```bash
# 严格文件清单(feat commit 必须改 15 文件)
git diff <feat-sha>^..<feat-sha> --name-only | sort
# 期望(15 文件):
#   backend/tests/_db_url.py
#   backend/tests/_isolation.py        (新建)
#   backend/tests/conftest.py
#   backend/tests/test_analytics.py
#   backend/tests/test_attachments.py
#   backend/tests/test_capacity.py
#   backend/tests/test_chat_tools.py
#   backend/tests/test_daily_report_relations.py
#   backend/tests/test_kpi_phase9.py
#   backend/tests/test_me_deletions.py
#   backend/tests/test_notifications.py
#   backend/tests/test_okr.py
#   backend/tests/test_phase10_dept_group.py
#   backend/tests/test_retro.py
#   backend/tests/test_sprints.py

# 零 src 闸门
git diff <feat-sha>^..<feat-sha> -- backend/app/ backend/alembic/ frontend/ DEPLOY.md README.md backend/.env backend/.env.example   # 必须完全空
```

---

## §6 防越界红线(28 项,任何一项触发立即驳回)

1. ❌ 改 `backend/app/` 任何文件
2. ❌ 改 `backend/alembic/` 任何 migration
3. ❌ 改 `frontend/` 任何文件
4. ❌ 改 `DEPLOY.md` / `README.md` / `backend/.env` / `backend/.env.example`(T-1102 已闭环议题,不重做)
5. ❌ 改 `backend/tests/` 上述白名单 13 文件 + `_isolation.py`(新建)+ `_db_url.py` 之外的任何 test
6. ❌ 改 `backend/conftest.py` 之外的任何 conftest(若存在嵌套)
7. ❌ 改任何 `docs/T-1XXX_spec.md` 历史契约
8. ❌ 自动 `git push`
9. ❌ 自启 T-1104 任何后续任务
10. ❌ revert `8459a5b` / `b5e77c3` / `c9693a9` / `1c67bd4` / `19ac08e` / `8d69ca8` / `ddc41ba` / `9f6ab11` 任何 commit
11. ❌ 在 feat / chore commit 之外打额外提交(`chore(lock)` 已由指挥官代办)
12. ❌ 篡改 §3.1 `_isolation.py` 字面量(包括 28 项字段 list / 顺序 / 注释 / docstring)
13. ❌ 把 `clean_external_settings` 改为 lambda / inline expression(必须独立函数)
14. ❌ 在 `_isolation.py` 顶部 import `app.config`(必须延迟 import,防循环依赖)
15. ❌ 把 `_EXTERNAL_SETTINGS_FIELDS` 扩展超过 28 项(加 `database_url` / `redis_url` / `jwt_secret_key` / `aipm_env` 等核心字段会破坏 fixture / test 自身)
16. ❌ 把 `_EXTERNAL_SETTINGS_FIELDS` 收缩到不足 28 项(覆盖不全 = 议题 A 修复不彻底)
17. ❌ 把 conftest.py autouse fixture scope 改为 module / session(必须 function scope,与 monkeypatch 兼容)
18. ❌ 把 fixture name 从 `_isolation_external_settings` 改为公开名(下划线前缀表示内部)
19. ❌ **不**移除 test_notifications.py:111-134 `_clean_notification_settings` fixture(必须去重,单一真理源)
20. ❌ 把 11 处替换为不同字面量(必须**完全统一** `derive_test_database_url(settings.database_url)`)
21. ❌ 用 sed / awk / 一刀切批量 replace(必须 Read + 精确 Edit 每处,逐文件审计)
22. ❌ 在某文件 import 区把 `from tests._db_url import derive_test_database_url` 放错位置(必须在 `from app.config import settings` 之后)
23. ❌ 在 commit message 中省略 `Worker timestamp:` 行
24. ❌ 写极简一行 commit message(必须 multi-line body,**特别提醒**:T-1102 chore commit 因极简扣分,本任务 commit body 必须含完工概要 + 文件清单)
25. ❌ 动 4 既定 untracked 文件 + `.claude/` 项目级 ECC symlinks
26. ❌ 改 `notify_service` / `oss_service` / `xunfei_asr` / `gemini_asr` / 任何业务逻辑
27. ❌ 11 处某文件没加 import(只替换 .replace 那行,**会引发 NameError**,Worker 必须双行同时改)
28. ❌ 把 dev_tasks.md 中 Task 1/2 的 `[x]` 状态字符或验收回执回滚为 `[ ]` / `[/]`(历史已闭环,不动)

---

## §7 commit message 序列(逐条字面量)

**Commit 1**(feat,改 15 文件):

```
fix(tests): T-1103 testsuite-wide isolation hardening — global _isolation_external_settings autouse fixture + 11 derive_test_database_url cutovers

[完整 body 见 §4 Step 6]

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

**Commit 2**(chore,改 `dev_tasks.md`):

```
chore(progress): close T-1103 — Phase 11 测试隔离全局化 + 议题 C 残留 11 处收口

[完整 body 见 §4 Step 7]

Worker timestamp: [YYYY-MM-DD HH:MM:SS]
```

**严禁**:仅一行 commit message(对比 T-1005/T-1007/T-1008/T-1101 风格,**收紧审计可读性**;T-1102 chore commit 体偏简已被记一分,本任务必须含完工概要 + 文件清单)。**严禁**省略 `Worker timestamp:` 行。

---

## §8 验收清单(指挥官二次验收用,28 项)

| # | 项 | 通过条件 |
|---|---|---|
| 1 | commit 链路 | HEAD 在 chore(spec): T-1103 契约起草 commit 之后 = 2 个 Worker commit(feat + chore) |
| 2 | feat commit 文件数 | 严格 = 15 文件(_isolation.py 新建 + _db_url.py + conftest.py + test_notifications.py + 11 个其他 test file),无第十六个文件夹带 |
| 3 | chore commit 文件数 | 严格 = 1 文件(`docs/dev_tasks.md`),无其他夹带 |
| 4 | 零 src 改动 | `git diff <feat>^..<feat> -- backend/app/ backend/alembic/ frontend/ DEPLOY.md README.md backend/.env backend/.env.example` 完全空 |
| 5 | `_isolation.py` 关键字面量 | grep `def clean_external_settings` 1 hit + grep `_EXTERNAL_SETTINGS_FIELDS` 至少 2 hit(定义 + 引用) |
| 6 | `_isolation.py` 28 项字段 | `grep -E '^    "[a-z_]+",' backend/tests/_isolation.py \| wc -l` = 28 |
| 7 | `_isolation.py` 8 类别注释 | grep `企业微信\|钉钉\|邮件 SMTP\|大模型网关\|讯飞 ASR\|OSS 对象存储\|ERP webhook\|Sentry` 共 8 hit |
| 8 | `_isolation.py` 延迟 import | `from app.config import settings` 出现在函数体内(非顶部) |
| 9 | conftest.py 加 import | grep `from tests._isolation import clean_external_settings` 1 hit |
| 10 | conftest.py autouse fixture | grep `_isolation_external_settings(monkeypatch)` 1 hit + 装饰器 `@pytest.fixture(autouse=True)` 紧邻 |
| 11 | test_notifications.py 去重 | grep `_clean_notification_settings` 在 test_notifications.py 中 **0 hit**(已移除) |
| 12 | test_notifications.py 行数减少 | `git diff <feat>^..<feat> -- backend/tests/test_notifications.py --stat` 应有 24+ 行删除 |
| 13 | `_db_url.py` docstring 同步 | grep `T-1103 议题 B(扩展为全仓 13 处)` 在 _db_url.py 中 1 hit |
| 14-24 | 11 处 test file 切换(逐文件) | 每文件:① grep `from tests._db_url import derive_test_database_url` 1 hit;② grep `TEST_DATABASE_URL = derive_test_database_url(settings.database_url)` 1 hit;③ grep `replace.*aipm_db.*aipm_db_test` 0 hit |
| 25 | 全仓零残留 | `grep -rn 'replace.*aipm_db.*aipm_db_test' backend/tests/ --include='*.py' \| grep -v '_db_url.py' \| wc -l` = 0 |
| 26 | ruff / mypy | `ruff check tests/` All passed + `mypy tests/_isolation.py tests/conftest.py` 0 error |
| 27 | pytest 全套 | `pytest -q` 必须 0 failed, 178 passed, 2 skipped(零回归) |
| 28 | Worker timestamp 双 commit + multi-line body | feat + chore 均含 `Worker timestamp: [...]` 行 + **chore commit body 非极简一行**(必须含完工概要 + 文件清单,对比 T-1102 chore body 减分) |

**全 28 项 PASS** → 验收通过 → Phase 11 第三任 Task 收口。

---

## §9 风险与回滚

### 风险

1. **`_isolation_external_settings` autouse 与 `test_asr.py` 已有 setattr 冲突**(低度):本 fixture 先 setattr 空值,test 内自己再 setattr 真值,理论上 later wins。但若某 test 期望"完全不被 monkeypatch 触碰"特定字段(罕见),可能冲突。
   - 缓解:§5 闸门 ⑤ 抽样跑 `pytest tests/test_asr.py -v` 验证 33 个 case 全 passed。若失败,Worker 应在终端打印失败 case 名 + traceback,**停手等待指挥官诊断**,**不**自行扩大 fixture scope 或缩小 `_EXTERNAL_SETTINGS_FIELDS`。

2. **`conftest.py` autouse fixture 与 test 模块内 fixture 顺序冲突**(低度):pytest fixture 解析顺序为 conftest.py 优先,但若某 test 模块内有同名 fixture,可能覆盖。已检查 11 处 test file 中无同名 fixture。
   - 缓解:fixture name `_isolation_external_settings` 下划线前缀 + 独特命名,**99%** 无冲突。若出现,Worker 应停手报指挥官。

3. **11 处 test file import 顺序错误**(中度):若 Worker 把 `from tests._db_url import` 放在 `from app.config import settings` **之前**,可能引发 `ImportError: cannot import name 'settings'`(因 `_db_url.py` 启动时不依赖 settings,但若某 test 先 import _db_url 再 import settings,语义上 OK 但顺序丑)。
   - 缓解:§3.5 字面量明确「在 `from app.config import settings` 之后」插入,Worker 严格按表执行。

4. **`_clean_notification_settings` 移除后 test_notifications.py 仍 pass 但 isolation 实际由 conftest.py 提供**(语义验证,非 bug):Worker 应在 §5 闸门 ⑤ 验证 `pytest tests/test_notifications.py -v` 全 passed,且 `test_notify_unconfigured_channels_skipped` 仍 1 passed(由 conftest.py autouse fixture 提供 isolation)。

5. **议题 B 漏文件**(中度):若 Worker 漏改某文件(如忘了 test_okr.py),`grep -rn 'replace.*aipm_db'` 仍命中。
   - 缓解:§5 闸门 ④ 强制 zero-hit gate,Worker 提交前必跑。

### 回滚

- **feat commit 回滚**:`git revert <feat-sha>` —— 15 文件回滚,helper + 全部 test 改动恢复原状。回滚后:议题 A 失效(test 又依赖跑测试者 .env)+ 议题 B 失效(11 处又是 .replace 硬编码)。
- **chore commit 回滚**:`git revert <chore-sha>` —— 回滚 `dev_tasks.md` Task 3 状态字符 + 锚点。
- 零 src 改动,零 alembic 改动,**回滚 0 风险**。

---

## §10 📣 给 Worker (Codex) 的物理交接单

> **指挥官签字时间戳**:`[2026-05-28 18:25:08]`
> **持牌任务**:**T-1103**(Phase 11 **第三任** — 测试隔离 fixture 全局化 + T-1102 议题 C 残留 11 处统一收口,**零业务 src 改动**)

- **执行入口**:**必须读完整** `docs/T-1103_spec.md`(本文件 ~600 行,10 章 + 📣 附录)。**必须**在改动前跑前置探针(`git status --short --branch` / `git log -3 --oneline` / `git diff` / `git diff --cached`),核验 HEAD = `chore(spec): T-1103 契约起草` commit 之后,工作树干净(`dev_tasks.md` Task 3 已被指挥官加锁 `[/]`),4 既定 untracked + `.claude/` 保留。

- **核心动作**(2 commit / 16 文件 = 1 helper 新建 + 1 helper 注释更新 + 1 conftest.py + 1 test_notifications 去重 + 11 test_*.py 切换 + 1 dev_tasks.md):

  **Commit 1 (fix)** — `fix(tests): T-1103 testsuite-wide isolation hardening — global _isolation_external_settings autouse fixture + 11 derive_test_database_url cutovers`:

  **议题 A 主修复**(优先做):
  1. **新建** `backend/tests/_isolation.py`(spec §3.1 完整字面量,~80 行,**28 项**字段顺序锁定:wechat 6 + dingtalk 5 + smtp 4 + new_api 2 + xunfei 3 + oss 5 + erp 1 + sentry 2)。
  2. **改** `backend/tests/conftest.py`:
     - 在 `from tests._db_url import derive_test_database_url`(T-1102 已加)之后插入 `from tests._isolation import clean_external_settings`(§3.2.1)。
     - 在 `setup_test_db` fixture 体结束之后(`await test_engine.dispose()` 后)/ `db_session` fixture 之前,插入 `_isolation_external_settings(monkeypatch)` autouse fixture(§3.2.1 完整字面量)。
  3. **改** `backend/tests/test_notifications.py`:**整段删除** L111-134 共 24 行 `_clean_notification_settings` fixture(§3.3.1)。保留 L109 `await engine.dispose()` + L135 空行 + L136 `@pytest.mark.asyncio` 不动。

  **议题 B 主修复**:
  4. **改** `backend/tests/_db_url.py`:更新 L4-7 docstring 4 行 → 5 行(§3.4 字面量,纯注释同步)。
  5. **改** 11 处 test file(§3.5 表 #1~#11),每文件 **逐文件 Read + 精确 Edit**:
     - test_okr.py(L33)
     - test_daily_report_relations.py(L34)
     - test_analytics.py(L23)
     - test_sprints.py(L42)
     - test_retro.py(L34)
     - test_capacity.py(L43)
     - test_kpi_phase9.py(L31)
     - test_phase10_dept_group.py(L44)
     - test_attachments.py(L32)
     - test_chat_tools.py(L27)
     - test_me_deletions.py(L21)

     每文件 2 行变更:① 在 `from app.config import settings` 之后插入 `from tests._db_url import derive_test_database_url`;② 替换 `TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")` 为 `TEST_DATABASE_URL = derive_test_database_url(settings.database_url)`。

  **Commit 2 (chore)** — `chore(progress): close T-1103 — Phase 11 测试隔离全局化 + 议题 C 残留 11 处收口`:
  6. **改** `docs/dev_tasks.md`:Phase 11 Task 3 (T-1103) `[/]` → `[x]`,标题改为 `**Task 3 (T-1103): 测试隔离 fixture 全局化 + T-1102 议题 C 残留 11 处 .replace 硬编码收口** — Done by Codex [YYYY-MM-DD HH:MM:SS]`;**保留**子 bullet 全部不动;在 📣 锚点段重写为「Phase 11 T-1103 完工,当前无持牌任务」终态文字(参考 T-1102 chore commit 风格)。

- **严禁项**(违反立即驳回,详见 §6 完整 28 项):
  - **严禁**改 `backend/app/` 任何文件。
  - **严禁**改 `backend/alembic/` 任何 migration。
  - **严禁**改 `frontend/` 任何文件。
  - **严禁**改 `DEPLOY.md` / `README.md` / `backend/.env` / `backend/.env.example`(T-1102 已闭环议题,不重做)。
  - **严禁**改 11 处之外的 test file(`test_distributed_lock.py` / `test_e2e_ipd.py` / `test_export_phase8.py` / `test_models_init.py` / `test_simulate_reports.py` / `test_deletion_cleanup.py` / `test_deletion_history.py` 无 `.replace` 硬编码,不动)。
  - **严禁**篡改 `_EXTERNAL_SETTINGS_FIELDS` 28 项(加 `database_url` 等核心字段会破坏 fixture / test 自身)。
  - **严禁**给 `_isolation_external_settings` fixture 加超范围操作(只调用 helper,不 inline setattr)。
  - **严禁** sed 一刀切批量 replace 11 处(必须 Read + 精确 Edit 每处)。
  - **严禁**在 11 处某文件没加 import(只替换 .replace 那行,会引发 NameError)。
  - **严禁** `_isolation.py` 顶部 import `app.config`(必须延迟 import 防循环依赖)。
  - **严禁**保留 test_notifications.py:111-134 `_clean_notification_settings` fixture(必须去重)。
  - **严禁** `git push`(留给指挥官决策推送时机)。
  - **严禁**自启 T-1104 / Phase 11 后续任务。
  - **严禁** revert `8459a5b` / `b5e77c3` / `c9693a9` / `1c67bd4` / `19ac08e` / `8d69ca8` / `ddc41ba` / `9f6ab11` 任何已落地 commit。
  - **严禁**在 feat / chore commit 之外打额外提交(`chore(lock)` 已由指挥官代办)。
  - **严禁**在两条 commit message 中遗漏 `Worker timestamp:` 行 或 写极简一行 commit message(T-1102 chore 已记一分,本任务必须含完工概要 + 文件清单)。
  - **严禁**改 dev_tasks.md Task 1 / Task 2 历史 `[x]` 状态或验收回执。

- **闸门**(全绿才提交,详见 §5):
  ```bash
  cd backend
  .venv/bin/ruff check tests/
  .venv/bin/mypy tests/_isolation.py tests/conftest.py
  .venv/bin/pytest -q   # 0 failed, 178 passed, 2 skipped

  # 议题 A 抽样
  .venv/bin/pytest -q tests/test_asr.py -v
  .venv/bin/pytest -q tests/test_notifications.py -v

  # 议题 B 全仓零残留(关键)
  cd ..
  grep -rn 'replace.*aipm_db.*aipm_db_test' backend/tests/ --include='*.py' | grep -v '_db_url.py'   # 必须 0 hit
  ```

  改动面校验:
  ```bash
  git diff <fix-sha>^..<fix-sha> --name-only | sort   # 严格 15 文件
  git diff <fix-sha>^..<fix-sha> -- backend/app/ backend/alembic/ frontend/ DEPLOY.md README.md backend/.env backend/.env.example   # 必须空
  ```

- **完工提交序列**(2 commit,顺序锁定):
  1. `fix(tests): T-1103 testsuite-wide isolation hardening — global _isolation_external_settings autouse fixture + 11 derive_test_database_url cutovers` —— **15 文件**。
  2. `chore(progress): close T-1103 — Phase 11 测试隔离全局化 + 议题 C 残留 11 处收口` —— **1 文件**(`dev_tasks.md`)。

  两条 commit message 都**必须**包含 multi-line body(参考 T-1101/T-1005/T-1008 风格,**特别**:chore commit body 必须含完工概要 + 文件清单)+ 末尾 `Worker timestamp: [YYYY-MM-DD HH:MM:SS]` 行。

- **时间戳纪律**:所有 commit message 末尾、终端汇报、`dev_tasks.md` 段落都必须带当前精确时间戳(`[YYYY-MM-DD HH:MM:SS]` 或 `[HH:MM:SS]`)。

- **完工后**:立即停手汇报「T-1103 完工,议题 A 全局 fixture + 议题 B 11 处统一收口,pytest 178 passed + 2 skipped 零回归。等待指挥官二次验收 + Phase 11 后续 task 起草」。**绝对不要**自启 T-1104。**绝对不要** `git push`。
