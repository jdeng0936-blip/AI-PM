# Alembic 数据库迁移规范

> Stage 4 文档。每一次 schema 变更都按本规范执行,避免重蹈 V2.0 发版前 `audit_logs` 险被误删的覆辙。

---

## 一、核心戒律(读完再写迁移)

### 1. 永远不要盲信 `--autogenerate`

`alembic revision --autogenerate` 是基于 ORM ↔ DB 双向比对生成 SQL。但 **autogenerate 有一个致命盲点**:

> 它只看 `Base.metadata.tables`,**不看你磁盘上的 model 文件**。

如果你新建了 `app/models/some_table.py`,但忘了在 `app/models/__init__.py` 加 import,
`Base.metadata` 不会感知到这个表 — autogenerate 就会认为它是 DB 里的"孤儿表",生成 `op.drop_table(...)`。

**🔴 真实事故**:V2.0 发版前 `audit_logs` 因此差点被 drop。详见 commit `b732ec2`。

### 2. 所有 `DROP` 操作必须人工审查

执行 `alembic upgrade head` 前,**逐行阅读** 新生成的迁移文件,重点看:

| 操作 | 风险等级 | 行动 |
|---|---|---|
| `op.drop_table(...)` | 🔴 致命 | 立即停手,99% 是 model 漏注册,不是真的要删表 |
| `op.drop_column(...)` | 🟠 高 | 确认该列是否真的从 ORM 移除;有数据需先备份 |
| `op.drop_index(...)` | 🟡 中 | 看是否影响查询性能 |
| `op.drop_constraint(...)` | 🟡 中 | 确认有无 FK 依赖此约束 |
| `op.alter_column(comment=...)` | 🟢 安全 | 元数据变更,放心 |

**自动化辅助**:`tests/test_models_init.py` 在 CI 阶段静态拦截 model 漏注册问题。但写迁移时仍需肉眼复核。

### 3. 大表索引必须 `CONCURRENTLY`

Postgres 默认建索引会锁表。对生产大表(>100w 行)直接 `CREATE INDEX` 可能阻塞业务数秒到数分钟。

```python
# ❌ 危险写法(生产大表)
op.create_index('ix_users_email', 'users', ['email'], unique=True)

# ✅ 安全写法 — alembic 自动生成的迁移需要手工改
def upgrade() -> None:
    # 必须先关掉 transaction(CONCURRENTLY 不能在 transaction 内执行)
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_email ON users(email)"
        )
```

**判断标准**:目标表行数 ≥ 10w → 强制 CONCURRENTLY。

### 4. `drop_constraint` + `create_index` 之间有锁窗口

V2.0 `schema_sync_v2_1_cleanup` 把 `users.dingtalk_userid` 从 UNIQUE CONSTRAINT 改为 UNIQUE INDEX,中间有数毫秒窗口。
本次安全是因为 `users` 表数据量小。生产大表同样操作要走两步:
1. 先 `CREATE UNIQUE INDEX CONCURRENTLY`
2. 等索引 valid,再 `DROP CONSTRAINT`(constraint 会自动用新 index)

---

## 二、标准工作流

### 2.1 准备阶段

```bash
cd backend

# 拉到最新 main(确保本地 alembic head 同步)
git pull origin main
PYTHONPATH=. .venv/bin/alembic current   # 看本地 head
PYTHONPATH=. .venv/bin/alembic check     # 应输出 "No new upgrade operations detected"
```

如果 `alembic check` 已经有未同步内容,**先解决再加新变更**,否则一次迁移混了两件事会很难回滚。

### 2.2 生成迁移

1. **改 ORM 模型**(在 `app/models/*.py` 里)
2. **如果是新 model 文件,立刻在 `app/models/__init__.py` 加 import**(这一步在 CI 会被 `test_models_init.py` 拦截)
3. 生成迁移:
   ```bash
   PYTHONPATH=. .venv/bin/alembic revision --autogenerate \
     -m "v2_1_<短描述,如 add_email_to_users>"
   ```

### 2.3 审查迁移文件(必做)

打开 `backend/alembic/versions/<新文件>.py`,逐项核对:

- [ ] **docstring 不是 template 占位**(`Alembic migrations script template`)— pre-commit 会拦截,但自己也要补真实说明
- [ ] **没有意外的 `drop_*` 操作**
- [ ] **大表索引已改成 CONCURRENTLY**
- [ ] **downgrade() 函数对称完整**,可回滚
- [ ] **Create Date / Revises 链接到上一个 head**

### 2.4 测试迁移

```bash
# 在本地真实跑一遍,看是否成功
PYTHONPATH=. .venv/bin/alembic upgrade head

# 再跑 alembic check,确认无残留 diff
PYTHONPATH=. .venv/bin/alembic check    # 必须输出 No new upgrade operations detected

# 验证 downgrade 也可用
PYTHONPATH=. .venv/bin/alembic downgrade -1
PYTHONPATH=. .venv/bin/alembic upgrade head
```

### 2.5 提交

```bash
git add backend/app/models/ backend/alembic/versions/<新文件>.py
git commit -m "feat(db): v2.x.x — <一句话描述这次 schema 变更>"
```

pre-commit hooks 会校验:
- 迁移文件不含 template docstring 占位
- 改了 model 文件就必须改 `__init__.py`(CI 二次兜底)

### 2.6 部署到生产前的检查清单

- [ ] **备份生产 DB** — 至少备份本次涉及的表
- [ ] **预演**:在 staging 环境跑 `alembic upgrade head` 并验证业务流程
- [ ] **回滚预案**:确认 `downgrade()` 能成功执行
- [ ] **大表索引**:确认所有索引都是 `CONCURRENTLY`
- [ ] **应用部署顺序**:DB migration → backend → frontend(避免新代码读不到旧 schema)

---

## 三、命名与组织

### 文件名

`alembic.ini` 配置:`file_template = %%(year)d%%(month).2d%%(day).2d_%%(hour).2d%%(minute).2d_%%(rev)s_%%(slug)s`

实际形如:`20260525_1027_d2c623c6291a_schema_sync_v2_1_cleanup.py`

### Revision ID 命名

- **简短功能描述**:`v2_1_notification_read_at`、`v2_0_baseline`
- **autogenerate hash**:`d2c623c6291a`(可读性差,建议手工 rename revision id 为业务可读名)

### 提交粒度

- 一次 commit = 一次原子 schema 变更
- **不**把"加列 + 加表 + 改约束"塞在同一个迁移里 — 出问题时无法精准回滚
- 大重构拆成多个有序迁移

---

## 四、紧急情况处理

### Q1: 误生成了 `op.drop_table('xxx')`

**不要 upgrade**。99% 是 model 漏注册。

```bash
# 1. 删除错误迁移文件
rm backend/alembic/versions/*_<错误的slug>.py

# 2. 修 app/models/__init__.py 加上 import
# 3. 重新 autogenerate
PYTHONPATH=. .venv/bin/alembic revision --autogenerate -m "..."
```

### Q2: 已经 upgrade 了错误迁移

立即 downgrade:
```bash
PYTHONPATH=. .venv/bin/alembic downgrade -1
```

如果 downgrade 也失败(表已被删):从备份恢复。这就是为什么 §2.6 第 1 条必须有备份。

### Q3: 多人协作出现分叉(branch)

```bash
PYTHONPATH=. .venv/bin/alembic heads
# 看到 2 个 head 就是分叉了
```

合并:
```bash
PYTHONPATH=. .venv/bin/alembic merge -m "merge branches" <head1> <head2>
```

---

## 五、相关文档

- `docs/RELEASE_NOTES_V2.0.md` — V2.0 完整迁移链与上线动作清单
- `backend/alembic/env.py` — Alembic 配置入口
- `backend/tests/test_models_init.py` — Model 注册完整性回归测试(CI 兜底)
- `.pre-commit-config.yaml` — `alembic-no-template-placeholder` hook
