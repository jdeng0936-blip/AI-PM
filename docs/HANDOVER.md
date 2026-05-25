# AI-PM 项目交接文档(HANDOVER)

> **场景**:原作者完成了本地 MVP 业务验证,代码 + 文档 + CI/CD + 应急预案均已就绪。
> 公有云 ECS 部署 / 上线后运维 / 业务推广 由本文档接收人负责。
>
> **代码当前版本**:`main` 分支,最新 tag `v2.0.0`。Phase 2.0(Pre-flight 生产就绪)已完成。
> **当前未做**:从未真实部署到公网 ECS。所有 V2.1 工件都已就绪,但都是"代码已写好,等人去跑"。
>
> **接收人**:你(运维 / 后端负责人)。
> **移交人**:原作者(下称"对接人")。
> **目标**:让你在 1-2 个工作日内把项目从"本地能跑"变成"公网 HTTPS 上线 + 持续运行"。

---

## 一、5 分钟全貌

| 维度 | 现状 |
|---|---|
| 业务定位 | 徽远成内部 AI 项目管理系统(IPD 门径 + 双轨敏捷 + AI 复盘 + OKR + 资源水位)|
| 技术栈 | FastAPI(async) + PostgreSQL 16 + pgvector + Redis 7 + Next.js 15 + React 19 + APScheduler |
| 部署形态 | Docker Compose 单机部署(MVP 阶段不上 K8s)|
| 当前规模 | 0 用户(待你部署后导入种子数据)|
| CI/CD | GitHub Actions(`.github/workflows/ci.yml` + `release.yml`),v2.0.0 已绿 |
| 监控 | Sentry SaaS(backend + frontend 两个项目);`/health/detailed` 多维度健康检查 |
| 备份 | `backend/scripts/backup.sh` + `restore_drill.sh`,需 crontab 调起 |
| 已知风险 | 单机部署,SPOF;APScheduler 已加 Redis 分布式锁(为未来多副本预留)|

---

## 二、文档阅读顺序(强烈建议按这个顺序)

> 总时长约 2-3 小时。一次读完,再开始动手。

### 第 1 步:理解全局(40 分钟)
1. **`README.md`** — 项目定位 + 整体功能矩阵
2. **`docs/system-overview.md`** — 系统架构图,看后端/前端/DB/Redis/APScheduler 怎么串
3. **`docs/whitepaper-system-design.md`** — 设计白皮书,带你理解"为什么这么搭"

### 第 2 步:看代码现状(30 分钟)
4. **`docs/RELEASE_NOTES_V2.0.md`** — V2.0 发了什么,看现在系统能做什么
5. **`docs/implementation-plan.md`** — 各 Sprint 实现历程(可快速扫,知道每个功能是哪一周加的)

### 第 3 步:部署前必读(60 分钟,**重点**)
6. **`docs/PRODUCTION_DEPLOY.md`** ⭐ — **公网 ECS 9 步部署 SOP**,你会照着这份逐步操作
7. **`docs/SENTRY_SETUP.md`** — Sentry 接入步骤,部署前需要先建项目拿 DSN
8. **`docs/MIGRATION_GUIDE.md`** — Alembic 迁移规范,所有以后改 schema 都要遵守
9. **`DEPLOY.md`** — 单机/内网快速版部署(**不是公网生产版**,但能让你先在测试机跑一遍熟悉 docker compose 命令)

### 第 4 步:出事前必读(30 分钟,**重点**)
10. **`docs/INCIDENT_PLAYBOOK.md`** ⭐ — P0/P1 应急 SOP、数据恢复、回滚、紧急 bug 修复
11. **本文档(HANDOVER.md)的第七节** — 已知陷阱

### 第 5 步:功能演化历史(选读,30 分钟)
12. **`docs/week4-chat-tools.md`** ~ **`docs/week8-capacity.md`** — 各 Sprint 的功能 spec,日后排查 bug 用得着

---

## 三、必须向对接人索要的凭证清单

> **以下凭证全部 ⚠️ 未提交到 Git**,代码仓库里只有 `.env.example` 占位符版本。
> 部署前必须凑齐**全部 ⚠️ 项**,否则无法启动。
>
> **建议索要方式**:加密邮件 / 一次性密码分享工具(如 onetimesecret.com)/ 当面口头 + 写到本地密码管理器。
> **绝对禁止**:贴聊天群、贴飞书消息、贴邮件正文明文、提交到 Git。

### 3.1 必须 ⚠️(没有则启动失败)

| # | 字段(`.env` 中变量名)| 用途 | 在哪里申请 / 生成 |
|---|---|---|---|
| 1 | `POSTGRES_PASSWORD` + `DATABASE_URL` 中嵌入的密码 | PostgreSQL 主库密码 | **你自己生成**:`openssl rand -base64 24`(不要用对接人本机的密码)|
| 2 | `JWT_SECRET_KEY` | JWT 签名密钥 | **你自己生成**:`openssl rand -hex 32` |
| 3 | `LITELLM_BASE_URL` + `LITELLM_API_KEY` | LLM 调用网关 | 向对接人索要(他知道徽远成内部 LiteLLM 的 URL + key)|
| 4 | `SENTRY_DSN`(backend Python 项目)| 后端错误监控 | 向对接人索要;若他没建,你自己去 https://sentry.io 建 |
| 5 | `NEXT_PUBLIC_SENTRY_DSN`(frontend React 项目)| 前端错误监控 | 同上,**两个 DSN 不能用同一个** |
| 6 | `WECHAT_CORP_ID` + `WECHAT_CORP_SECRET` + `WECHAT_AGENT_ID` + `WECHAT_TOKEN` + `WECHAT_ENCODING_AES_KEY` | 企微回调 + 推送 | 向对接人索要(徽远成企微管理后台 → 自建应用)|
| 7 | `OSS_ENDPOINT` + `OSS_BUCKET` + `OSS_ACCESS_KEY` + `OSS_SECRET_KEY` | 附件 + 语音 + 企微素材 | 向对接人索要(徽远成阿里云 OSS)|

### 3.2 强烈建议 ⚠️(没有则**部分功能降级**)

| # | 字段 | 没有的后果 | 在哪拿 |
|---|---|---|---|
| 8 | `WECHAT_BOT_WEBHOOK` | 战情日报 / 风险预警群推失效(走 skipped)| 企微群 → 群机器人 |
| 9 | `DINGTALK_BOT_WEBHOOK` + `DINGTALK_BOT_SECRET` | 钉钉通知失效(走 skipped)| 钉钉群 → 智能群助手 |
| 10 | `XUNFEI_APP_ID` + `XUNFEI_API_KEY` + `XUNFEI_API_SECRET` | 语音 ASR 不可用,日报录音转写禁用 | 向对接人索要(讯飞控制台)|
| 11 | `SMTP_SERVER` + `SMTP_USER` + `SMTP_PASSWORD` + `SMTP_FROM_EMAIL` | 邮件降级通道失效,纯内网测试可不配 | 向对接人索要 |

### 3.3 可选(高级特性)

| # | 字段 | 说明 |
|---|---|---|
| 12 | `DINGTALK_APP_KEY` + `DINGTALK_APP_SECRET` + `DINGTALK_AGENT_ID` | 钉钉企业应用,精准推送给个人(只有群推也能用)|
| 13 | `BACKUP_OSS_BUCKET` | 备份自动上传 OSS(不配则只本地 14 天滚动)|

### 3.4 索要凭证时的话术模板

> "Hi,我现在接手 AI-PM 的公网部署,需要以下凭证。请通过 [加密邮件 / onetimesecret] 发我:
>
> **必须**:
> - LiteLLM 网关 URL + key
> - Sentry 两个 DSN(backend / frontend)
> - 企微自建应用 5 项(CORP_ID / CORP_SECRET / AGENT_ID / TOKEN / ENCODING_AES_KEY)
> - OSS 4 项(endpoint / bucket / access key / secret key)
>
> **建议**:
> - 企微群机器人 webhook
> - 钉钉群机器人 webhook + secret
> - 讯飞 ASR 3 项
>
> 收到后我会落到生产 ECS 上的 `/opt/aipm/backend/.env`,文件权限 `chmod 600`,只 root + aipm-user 能读。"

---

## 四、部署执行顺序(对照 PRODUCTION_DEPLOY.md)

> 这部分是 `docs/PRODUCTION_DEPLOY.md` 的"导航",不重复内容。出问题查 `docs/INCIDENT_PLAYBOOK.md`。

```
Phase 2.1 部署流程(预计 1 个工作日)
├── 上线前 checklist(读 PRODUCTION_DEPLOY.md 第一节)
│   ├── 公有云 ECS:4 vCPU / 8 GB RAM / 100 GB SSD 起步
│   ├── 公网 IP + 80/443 安全组放行,其它端口全关
│   ├── 域名 A 记录指向 ECS IP
│   ├── SSH key 登录 + 关闭密码登录
│   ├── 时区 Asia/Shanghai
│   └── 凭证全部索要齐(对照本文档第三节)
│
├── 软件依赖
│   ├── Docker ≥ 24 + Compose v2.20+
│   ├── postgresql-client-16(备份用)
│   └── ossutil(可选,自动上传备份)
│
├── 9 个 Step(对照 PRODUCTION_DEPLOY.md 第二节)
│   ├── Step 1:git clone 到 /opt/aipm
│   ├── Step 2:cp .env.production.template → .env,逐字段填(本文档第三节凭证)
│   ├── Step 3:bash scripts/preflight.sh(校验 .env 完整性)
│   ├── Step 4:docker compose -f docker-compose.prod.yml -f docker-compose.prod.https.yml up -d
│   ├── Step 5:docker exec aipm-backend alembic upgrade head + alembic check
│   ├── Step 6:python scripts/seed_admin.py(交互式建第一个 admin)
│   ├── Step 7:curl https://<域名>/health/detailed(全绿)
│   ├── Step 8:确认 APScheduler 11 个任务全部注册
│   └── Step 9:Sentry 收到第一条测试事件
│
├── crontab(读 PRODUCTION_DEPLOY.md 第三节)
│   ├── 每日 03:00 backup.sh
│   └── 每周一 04:00 restore_drill.sh
│
└── 第一周观察(读 PRODUCTION_DEPLOY.md 第四节)
    └── 每天检查:/health/detailed + Sentry P0/P1 + DB 行数 + APScheduler 日志 + 备份文件
```

---

## 五、Day 2 起的常规运维责任

| 频次 | 任务 | 在哪 |
|---|---|---|
| 每天 | 看 `/health/detailed`,确认全绿 | 自建监控 / Uptime Robot |
| 每天 | 看 Sentry 24h Issue 数,P0/P1 立即响应 | Sentry web UI |
| 每周 | 看 `restore_drill.sh` 上周日志,确认演练通过 | `/var/log/aipm-restore-drill.log` |
| 每周 | 看 `audit_logs` 行数增长是否符合预期 | `docker exec aipm-postgres psql ...` |
| 每月 | 看 `audit_logs_archive` 表是否在归档(>12 个月数据自动迁移)| 同上 |
| 每月 | 看磁盘使用,> 70% 报警 | `df -h` |
| 每季度 | 升级 Docker / OS 安全补丁 | `apt upgrade` |
| 每次升级 | 严格走 `INCIDENT_PLAYBOOK.md` 第四节 hotfix SOP | — |

---

## 六、CI/CD 流程(已建好,你只需了解)

- **CI 触发条件**:任何分支 push + main PR
- **CI 内容**(`.github/workflows/ci.yml`):
  - Backend:postgres:16 + redis:7 容器 + `alembic upgrade head` + `alembic check` + `pytest` + `ruff check`
  - Frontend:`npm run typecheck` + `npm run lint` + `npm run build`
- **Release 触发条件**:push `v*` tag(`.github/workflows/release.yml`)
  - 自动从 `docs/RELEASE_NOTES_V{major.minor}.md` 取 body 生成 GitHub Release
- **本地预提交**(`.pre-commit-config.yaml`):
  - ruff + ruff-format + check-yaml(排除 docker-compose)+ check-added-large-files(500KB 上限)
  - 自定义:拦截 alembic 模板 docstring + 拦截 `.env` 文件实值提交

---

## 七、已知陷阱 & 必须知道的细节

### 7.1 ⚠️ `backend/.env` 永远不能提交

- 已被 `.gitignore` 拦截 + `.pre-commit-config.yaml` 中 `no-real-env-files` 钩子双保险
- 仅 `.env.example` 和 `.env.production.template` 允许提交
- **不要为了图方便用 `git add .` 然后 `git commit -a` 绕开 pre-commit**

### 7.2 ⚠️ Alembic baseline 是 `create_all`,后续迁移必须幂等

- `v2_0_baseline` 用 `Base.metadata.create_all()` 建全部表(快速 bootstrap)
- 所有后续 migration **必须**用 `inspector.get_table_names() / get_columns() / get_unique_constraints()` 检查再 add/drop
- 否则 CI 上跑 `alembic upgrade head` 会因 `DuplicateColumn` 失败(已踩过坑,见 commit `40110c7`)
- 写新迁移时**抄** `audit_logs_archive_table.py` 或 `schema_sync_v2_1_cleanup` 的幂等模式
- **详见** `docs/MIGRATION_GUIDE.md`

### 7.3 ⚠️ APScheduler 11 个任务都带 Redis 分布式锁

- `backend/app/services/distributed_lock.py` 实现 Redis SETNX 锁,TTL 30 分钟
- Redis 挂了**会优雅降级**(直接执行任务,不阻塞业务)
- 多副本部署时锁防止重复执行;**当前单机部署用不到,但代码已就绪**

### 7.4 ⚠️ pgvector 维度可配置

- `EMBEDDING_DIM=1536` 是默认值(OpenAI ada-002 / text-embedding-3-small)
- 改为 3072(text-embedding-3-large)或 1024(智谱)需要**新写一条 alembic migration**:`ALTER COLUMN ... TYPE vector(N)`
- 直接改 `.env` 而不改 schema 会导致写入失败

### 7.5 ⚠️ docker-compose `!reset` 标签

- `docker-compose.prod.https.yml` 用了 YAML 的 `!reset` 自定义 tag 来清空 ports 暴露(走 Caddy)
- PyYAML 不认这个 tag → `.pre-commit-config.yaml` 已 `exclude: ^docker-compose.*\.yml$` 跳过 check-yaml
- 你想新加 docker-compose 文件时,记得保留这条 exclude

### 7.6 ⚠️ 生产模式 `lifespan` 跳过建表

- `AIPM_ENV=dev` → `init_db()` 自动建缺失表(本地图省事)
- `AIPM_ENV=prod` → **跳过** `init_db()`,**必须**先手动 `alembic upgrade head`
- 漏了就启动报"relation does not exist"

### 7.7 ⚠️ 回滚操作(`alembic downgrade`)有数据损失风险

- "新增列被删 = 该列数据没了"
- 优先**向前 hotfix**,**只有 V2.x 引入了不可恢复损坏**时才回滚
- 回滚 SOP 详见 `INCIDENT_PLAYBOOK.md` 第五节

### 7.8 ⚠️ 通知降级链路

- 通知服务有 `wechat > dingtalk > email > skipped` 的降级链
- 任一渠道失败自动降下一级,**不会阻塞业务**
- 但你看 Sentry 应该会看到 "channel failed" warning,需要关注

---

## 八、联系人 & 升级链路

| 角色 | 谁 | 何时联系 |
|---|---|---|
| 业务 owner / 决策 | 对接人 jdeng | "是否对用户公开 X / 是否回滚 / 是否扩容" |
| 代码 / Alembic / 后端 | 对接人 jdeng | 凭证 / 历史决策 / 业务规则 |
| 前端 / Sentry | 对接人 jdeng | 同上 |
| 公有云 / DNS / 证书 | 你 | 全部 |
| oncall 一线 | 你 | 任何 P0/P1 |
| 数据库 / 备份 / 恢复 | 你 | 任何 DB 异常 |

**遇到不确定的业务规则 → 找 jdeng 而不是猜。**

---

## 九、交接 checklist(完成一项打 ✅)

```
□ 已读完第二节列出的 11 篇文档
□ 已索要并存好第三节列出的所有凭证(密码管理器,非聊天群)
□ 已在本机用 DEPLOY.md(单机版)成功 docker compose up 一次(预演)
□ 已开通 ECS,完成 80/443 安全组 + DNS A 记录 + SSH key
□ 已按 PRODUCTION_DEPLOY.md Step 1-9 完成首次部署
□ /health/detailed 已全绿
□ Sentry 已收到第一条事件
□ crontab 已加 backup.sh + restore_drill.sh
□ 已和 jdeng 同步部署完成 + 公网 URL
□ 上线第一周每日 checklist 已建立(可用日历提醒)
```

---

**最后一句**:这套系统已经把"能脱手的"都脱手成代码 / 文档 / CI / 应急预案了。你接手后,稳定性主要看你**每周做不做 `restore_drill`** + **每天看不看 `/health/detailed`**。这两件事不做,出事就是数据丢失;做了,大事化小。

部署遇到任何困惑,先翻 `INCIDENT_PLAYBOOK.md`,翻完还没答案再 ping jdeng。
