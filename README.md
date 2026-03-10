# 徽远成 AI-PM — 智能项目管理系统

> 基于 FastAPI + Gemini 多模态 + 企业微信，替代 Excel 日报填报的 AI 驱动项目管理 SaaS。

## 功能
- 📱 **企微入口**：员工直接在企微发送自然语言日报（文字/图片/语音）
- 🤖 **AI 质检**：自动解析并校验汇报完整性，不合格立即退回+给出修改模板
- 📊 **管理晨报**：管理层每日在看板查看全员进展、未汇报名单、卡点预警
- 🏗️ **IPD 门径管理**：5阶段4关卡 + 软硬双轨敏捷，日报自动聚合为项目健康度
- 🔗 **ERP 联动**：物料到货自动解除硬件等待卡点
- 🔒 **Token 熔断**：每日 AI 调用量自动限流，成本可控

## 技术栈
| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 / FastAPI / AsyncSession |
| 数据库 | PostgreSQL 15 + JSONB |
| 缓存 | Redis 7 |
| AI 引擎 | NewApi → Gemini 1.5 Pro |
| 部署 | Docker + docker-compose |

---

## 🚀 开发环境启动（本地）

> ⚠️ 每一步都必须按顺序执行，否则会出现 "Table not found" 错误。

```bash
# ── Step 1: 配置环境变量 ─────────────────────────────────────────
cd backend && cp .env.example .env
# 编辑 .env，填写企微、NewApi、数据库连接等配置

# ── Step 2: 启动本地 PostgreSQL & Redis ──────────────────────────
# 如果没有本地 PG/Redis，可以用 Docker 单独启动：
docker run -d --name pg-dev -e POSTGRES_USER=aipm -e POSTGRES_PASSWORD=devpass \
    -e POSTGRES_DB=aipm_db -p 5432:5432 postgres:15-alpine
docker run -d --name redis-dev -p 6379:6379 redis:7-alpine

# ── Step 3: 创建虚拟环境并安装依赖 ────────────────────────────────
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# ── Step 4: 【关键】执行数据库迁移，创建所有表 ─────────────────────
# ⚠️ 不执行这步直接启动服务，企微消息进来会崩溃 "Table not found"
alembic upgrade head

# ── Step 5: 启动开发服务器 ───────────────────────────────────────
uvicorn app.main:app --reload --port 8000
# 访问 API 文档：http://localhost:8000/docs
```

---

## 🌐 企微回调联通（内网穿透）

> ⚠️ **企微的腾讯服务器在公网，无法访问你的 `localhost:8000`。**
> 开发阶段必须使用内网穿透工具，否则企微后台"API接收消息"验证必定失败。

```bash
# ── 方案 A: Ngrok（推荐）──────────────────────────────────────
# 安装：https://ngrok.com/download
ngrok http 8000
# 会生成类似 https://a1b2c3d4.ngrok-free.app 的公网域名

# ── 方案 B: cpolar（国内更稳定）──────────────────────────────
# 安装：https://www.cpolar.com
cpolar http 8000
```

**然后在企微管理后台操作**：
1. 进入「应用管理」→ 你的自建应用 →「接收消息」→「设置API接收」
2. URL 填写：`https://a1b2c3d4.ngrok-free.app/api/v1/wechat/callback`
3. Token 和 EncodingAESKey 必须与 `.env` 中一致
4. 点击「保存」，系统会发 GET 验证请求，通过后即可收发消息

> 💡 生产部署后，换成徽远成自己的真实域名即可。

---

## 🏭 生产部署（Docker）

```bash
# ── Step 1: 配置环境变量 ─────────────────────────────────────────
cd backend && cp .env.example .env
# 编辑 .env，填写所有配置

# ── Step 2: 启动所有服务 ─────────────────────────────────────────
export POSTGRES_PASSWORD=your_secure_password
docker compose -f docker-compose.prod.yml up -d

# ── Step 3: 【关键】进入后端容器执行数据库迁移 ─────────────────────
docker exec -it aipm-backend alembic upgrade head

# ── Step 4: 验证服务 ──────────────────────────────────────────────
curl http://localhost:8000/health
# 预期返回：{"status":"ok","service":"huiyuancheng-ai-pm"}

# ── Step 5: 查看日志 ──────────────────────────────────────────────
docker compose -f docker-compose.prod.yml logs -f backend
```

---

## 🔄 数据库自动备份

> ⚠️ 备份脚本已适配 Docker 部署（通过 `docker exec` 进入容器执行 `pg_dump`）。
> **不要**在宿主机上直接运行 `pg_dump`，因为数据库在 Docker 容器内。

```bash
# 赋予执行权限
chmod +x scripts/pg_backup.sh

# 添加 crontab（在生产服务器上，不是 Mac 本地）
crontab -e
# 添加以下行（每日凌晨 3:00 自动备份）：
0 3 * * * /opt/aipm/scripts/pg_backup.sh >> /var/log/aipm_backup.log 2>&1
```

---

## 项目结构

```
backend/app/
├── main.py                    # FastAPI 入口（dev/prod 双模式）
├── config.py                  # 环境变量配置
├── database.py                # 异步数据库连接池
├── models/                    # SQLAlchemy ORM（9张表）
│   ├── user.py                #   员工表
│   ├── daily_report.py        #   AI 日报主表
│   ├── risk_alert.py          #   卡点预警表
│   ├── usage_log.py           #   Token 成本风控表
│   ├── project.py             #   IPD 项目总表
│   ├── project_stage.py       #   IPD 5阶段表
│   ├── gate_review.py         #   关卡评审记录表
│   ├── sprint.py              #   软件轨 Sprint 表
│   └── project_member.py      #   项目成员分配表
├── routers/                   # API 路由
│   ├── wechat.py              #   企微回调主网关 ⭐
│   ├── dashboard.py           #   管理晨报看板
│   ├── projects.py            #   IPD 项目管理 ⭐
│   ├── gates.py               #   关卡评审
│   ├── sprints.py             #   Sprint 敏捷管理
│   ├── erp.py                 #   ERP 联动
│   └── reports.py             #   日报 CRUD
├── services/                  # 业务逻辑
│   ├── ai_engine.py           #   大模型引擎 ⭐
│   ├── health_engine.py       #   日报→健康度聚合引擎 ⭐
│   ├── wechat_api.py          #   企微 API 工具
│   └── token_guard.py         #   Token 熔断守卫
└── middleware/
    └── rbac.py                #   RBAC 权限中间件
```

## API 文档

启动后访问：http://localhost:8000/docs
