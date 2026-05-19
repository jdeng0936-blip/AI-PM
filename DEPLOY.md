# AI-PM V2.0 部署指南

> 从 0 到上线的完整步骤,适合**第一次把 V2.0 部署到生产/内网/试用环境**的同学。
>
> 部署时间预估:
> - 准备凭证:30 分钟(企微/钉钉/OSS/LiteLLM)
> - 实际部署:15 分钟
> - 联调验证:30 分钟
> - **总计:约 1.5 小时**

---

## 一、部署前准备(必读)

### 1.1 准备清单

| 项 | 怎么准备 | 必需? |
|----|---------|-------|
| **服务器** | 4 核 8G + 50G SSD,Linux(Ubuntu 22.04+ 推荐) | ✅ |
| **域名 + SSL** | 解析到服务器,前端域名 + 证书(可用 Let's Encrypt) | ⭐ 推荐 |
| **Docker + docker compose** | 服务器装 docker 26+ + compose v2 | ✅ |
| **LiteLLM / NewAPI 网关地址 + API Key** | 已有(张毅部署的) | ✅ |
| **企微自建应用** | corp_id / corp_secret / agent_id / token / aes_key | ⭐ 推荐 |
| **企微群机器人 Webhook** | 群设置 > 添加机器人 > 自定义 | ⭐ 推荐 |
| **钉钉群机器人 Webhook + 加签 Secret** | 群设置 > 智能群助手 > 自定义 | ⭐ 推荐 |
| **阿里云 OSS** | bucket / access_key_id / access_key_secret | ⭐ 推荐 |
| **JWT 密钥** | `openssl rand -hex 32` 生成 | ✅ |

⭐ 推荐项不配也能跑,但对应功能会优雅降级(企微/钉钉推送 skip、OSS 走本地降级等)。

### 1.2 准备凭证的具体路径

| 凭证 | 获取地址 |
|------|---------|
| 企微 CorpID | https://work.weixin.qq.com → 我的企业 → 企业信息 |
| 企微 AgentID + Secret | 我的企业 → 应用管理 → 自建 → 应用详情 |
| 企微 Token + AESKey | 应用详情 → 接收消息 → 设置 API 接收 |
| 企微群机器人 | 群 → 群机器人 → 添加 → 自定义 → 复制 Webhook |
| 钉钉群机器人 | 群 → 群设置 → 智能群助手 → 添加 → 自定义 → 选加签 |
| 阿里云 OSS | https://oss.console.aliyun.com → Bucket + 子账号 RAM AccessKey |

---

## 二、部署流程

### Step 1:克隆代码到服务器

```bash
git clone <your-repo-url> aipm
cd aipm
git checkout main
```

### Step 2:准备 .env

```bash
cp backend/.env.production.template backend/.env
nano backend/.env  # 或用你顺手的编辑器
```

**必改的项**(搜索 `⚠️_` 一个个填):

- `POSTGRES_PASSWORD` — 强密码,至少 16 位
- `DATABASE_URL` — 把里面的密码换成上面同样的
- `JWT_SECRET_KEY` — 跑 `openssl rand -hex 32` 复制结果
- `LITELLM_API_KEY` — 你的 LiteLLM Key
- `CORS_ALLOWED_ORIGINS` — 改成 `["https://你的前端域名"]`

**推荐填的**(对应模块才能用):

- 企微 5 个字段
- 钉钉 2 个字段(webhook + secret)
- OSS 4 个字段

### Step 3:跑预检脚本

```bash
cd backend
bash scripts/preflight.sh
```

期待输出:
```
✅ 全部通过,可以上线!
```

如果有红色 ✗,按提示修;有黄色 ⚠ 可选择性修(不影响启动)。

### Step 4:一键启动

```bash
cd ..   # 回到项目根
docker compose -f docker-compose.prod.yml up -d --build
```

第一次会拉镜像 + 构建前后端,约 5-10 分钟。

### Step 5:跑数据库迁移(关键!)

```bash
docker exec aipm-backend alembic upgrade head
```

预期输出:
```
INFO  [alembic.runtime.migration] Running upgrade  -> 7c681b8e950c, Alembic migrations script template.
INFO  [alembic.runtime.migration] Running upgrade 7c681b8e950c -> v2_0_baseline, V2.0 baseline: 全表 + Week 1-8 schema 一次性建齐
```

验证:
```bash
docker exec aipm-postgres psql -U aipm -d aipm_db -c "\dt" | wc -l
# 应该 ≥ 20 张表
```

### Step 6:创建第一个 admin 账号

```bash
docker exec -it aipm-backend python scripts/seed_admin.py
```

按提示输入用户名 / 密码。

### Step 7:验证启动

```bash
curl http://localhost:8000/health
# 期待: {"status":"ok","service":"huiyuancheng-ai-pm"}

# 看定时任务有没启动(9 个)
docker logs aipm-backend 2>&1 | grep "APScheduler"
# 期待: ⏰ APScheduler 已启动,注册了 9 个定时任务
```

访问前端:`https://你的前端域名` → 用 admin 账号登录。

---

## 三、联调验证(逐项手工测)

### A. 基础功能(必过)

- [ ] admin 账号登录成功,跳转到 `/dashboard`
- [ ] 在 `/submit-report` 提交一份日报,AI 解析+评分正常
- [ ] 在 `/dashboard` 看到刚提交的日报
- [ ] 在 `/users` 创建 1 个普通员工账号
- [ ] 普通员工登录,只能看自己的日报

### B. Week 1-2:通知 + 催报

- [ ] admin 调 `POST /api/v1/notifications/test` 真发一条到企微/钉钉群
- [ ] 在 `.env` 改一下 cron 把 `remind_unreported_friendly` 改成下一分钟触发,测试催报触达

### C. Week 3:附件 + 语音

- [ ] `/submit-report` 上传一张图片,看是否进 OSS
- [ ] 自由模式录音 10s,看是否能转写出文字

### D. Week 4-5:Chat + OKR

- [ ] 在 `/chat` 问"本周谁延期最多",看 AI 是否调用 Tool 返回答案
- [ ] 在 `/okr` 建一个周期 + 目标 + KR
- [ ] 让 KR owner 提交一份日报,日报里提到 KR 的数值进展(如「推理延迟从 800ms 降到 450ms」),看 AI 是否自动更新 KR

### E. Week 6:复盘

- [ ] admin 在 `/retro` 点「✨ 生成复盘」→ 选 OKR 周期 → 等待生成
- [ ] 复盘 Markdown 正常显示,落入知识库

### F. Week 7:Sprint 燃尽

- [ ] 在 `/sprints` 选项目 → 创建任务 → 标记完成
- [ ] 点「🔄 刷新快照」生成燃尽数据
- [ ] 燃尽图正常显示理想 + 实际曲线

### G. Week 8:资源水位

- [ ] 在 `/capacity` 选 Sprint
- [ ] 给某员工分配超出容量的任务,看是否标红过载
- [ ] 点「✨ AI 调配建议」,看是否推荐转给闲置同事

### H. 定时任务(等真实触发)

- [ ] 看 `docker logs aipm-backend` 在 18:00 出现「Sprint 燃尽快照」日志
- [ ] 周一 09:00 收到周报推送
- [ ] 周一 08:30 看到水位刷新 + 过载预警(如有过载)

---

## 四、上线日推送给团队的话术

复制改一下:

```
🚀 各位同事:

徽远成 AI-PM V2.0 系统今天正式上线!

📅 日常使用:
• 早 9 点前 → ☀️ 晨规划 提交今天计划
• 晚 22 点前 → 🌙 晚复核 提交今天完成
• 17:30 未交 → 企微会自动友好提醒
• 22:00 仍未交 → 通知管理层

📊 评分由 AI 自动给出,均分:
• 80+ : 健康
• 60-79: 需关注
• <60: 直属主管会聊

🌟 V2.0 新功能(全员可用):
• 🎯 OKR 战略对齐 — 日报数据自动更新 KR 进度
• 🔥 Sprint 燃尽 — 任务级故事点跟踪 + 关键路径
• 🌡️ 资源水位 — 看自己负载,管理层看团队
• 🔁 AI 复盘库 — 周期/项目/月度/事故四类自动复盘
• 🤖 总经理 AI 战情助手 — 自然语言问任何业务问题

🐛 任何 Bug / 体验建议:
• 表单收集: [填你的反馈表单链接]
• 紧急问题: @张毅 / @admin

试用 2 周后我们会做第一次反馈复盘,持续打磨。

谢谢各位的支持!
```

---

## 五、运维 & 备份(上线后第一周)

### 5.1 每日备份

```bash
# 加进服务器 crontab(凌晨 3 点备份)
0 3 * * * docker exec aipm-postgres pg_dump -U aipm aipm_db | gzip > /backup/aipm_$(date +\%Y\%m\%d).sql.gz
0 4 * * 0 find /backup -name "aipm_*.sql.gz" -mtime +30 -delete  # 保留 30 天
```

### 5.2 日志查看

```bash
# 实时跟后端日志
docker logs -f aipm-backend

# 看定时任务执行情况
docker logs aipm-backend 2>&1 | grep "⏰"

# 看 AI 调用情况(成本控制)
docker logs aipm-backend 2>&1 | grep "Gemini 解析成功" | wc -l
```

### 5.3 监控指标

| 指标 | 命令 |
|------|------|
| 后端健康 | `curl http://localhost:8000/health` |
| 数据库大小 | `docker exec aipm-postgres psql -U aipm -d aipm_db -c "SELECT pg_size_pretty(pg_database_size('aipm_db'));"` |
| 日报数 | `docker exec aipm-postgres psql -U aipm -d aipm_db -tAc "SELECT COUNT(*) FROM daily_reports;"` |
| 通知发送数 | `docker exec aipm-postgres psql -U aipm -d aipm_db -tAc "SELECT status,COUNT(*) FROM notifications GROUP BY status;"` |

---

## 六、回滚预案

### 6.1 后端代码出问题

```bash
# 回到上一个版本
git log --oneline -5      # 找上一个 commit
git checkout <prev-commit-hash>
docker compose -f docker-compose.prod.yml up -d --build backend
```

### 6.2 数据库迁移出问题

```bash
# 降级到上一个版本
docker exec aipm-backend alembic downgrade -1

# 完全回退到 V1.0(谨慎!Week 1-8 数据会丢)
docker exec aipm-backend alembic downgrade 7c681b8e950c
```

### 6.3 数据恢复

```bash
# 从备份恢复(最近一次)
gunzip -c /backup/aipm_20260519.sql.gz | docker exec -i aipm-postgres psql -U aipm -d aipm_db
```

### 6.4 紧急关闭某个定时任务

定时任务出问题(如 LLM 网关挂导致周报刷屏),临时禁用:

```python
# 在 backend/app/services/scheduler.py 注释掉对应 add_job
# 或更简单:连进容器手工 kill
docker exec -it aipm-backend python -c "
from app.services.scheduler import scheduler
scheduler.pause_job('weekly_report_monday')
"
```

---

## 七、常见问题

### Q1: 启动后 9 个定时任务只显示 X 个?

A: 看 `docker logs aipm-backend` 找 `APScheduler` 日志。如果数量不对,检查 `scheduler.py` 有没语法错。

### Q2: 企微/钉钉推送收不到?

A:
1. admin 调 `POST /api/v1/notifications/channels` 看哪个渠道 `configured=false`
2. 调 `POST /api/v1/notifications/test` 真发一条,看 `tool_calls` 里的 error
3. 检查机器人加签 Secret 是否正确

### Q3: AI 解析特别慢 / 失败?

A: Gemini thinking model 一次调用 20-60s 正常。如果超过 120s 或一直失败:
1. 看 `docker logs aipm-backend | grep "Gemini"` 找异常
2. 检查 LiteLLM 网关是否在线
3. 临时降级:`.env` 改 `NEW_API_MODEL=gemini-2.5-flash`(去掉 thinking)

### Q4: OSS 上传失败但日报照样提交?

A: 这是设计的优雅降级 — OSS 失败时附件会落到 `LOCAL_UPLOAD_DIR`(容器内 `/app/uploads`),前端 URL 走 `/api/v1/attachments/local/...` 代理。生产建议建一个持久化 volume:

```yaml
# docker-compose.prod.yml 加
volumes:
  - uploads_local:/app/uploads
```

### Q5: 数据库越来越大?

A:
- `daily_reports.raw_input_text` 是大头 → 半年后可归档转移
- `notifications` 表无清理 → 6 个月以上的可清:
  ```sql
  DELETE FROM notifications WHERE created_at < NOW() - INTERVAL '6 months';
  ```
- `burndown_snapshots` Sprint 结束后保留即可,不爆炸

---

## 八、上线后 2 周的健康检查

| 时间点 | 看什么 |
|--------|--------|
| **Day 1 晚** | 当天日报数应该 ≥ 员工数 × 50%(适应期) |
| **Day 3** | 看 `notifications` 表 `failed` 状态多不多,排查推送问题 |
| **Day 7** | 周报推送成功?让管理层确认收到了 |
| **Day 14** | 看 admin 是否真的在用 `/chat` AI 对话,如果用得少需要培训 |

---

## 九、相关文档

| 文档 | 内容 |
|------|------|
| [docs/system-overview.md](docs/system-overview.md) | 应用场景全图,看懂整个系统 |
| [docs/week1-...week8-...md](docs/) | 每周开发的详细联调指南 |
| [docs/whitepaper-system-design.md](docs/whitepaper-system-design.md) | 产品白皮书 |
| [backend/.env.production.template](backend/.env.production.template) | 配置模板含详细注释 |
| [backend/scripts/preflight.sh](backend/scripts/preflight.sh) | 一键预检 |

---

## 十、收尾的话

V2.0 总共 8 周 / 30 个 atomic commit / 115 个测试 / 29 个 AI Tool / 9 个定时任务。

部署上去后,**让真实数据流动起来比再加功能更重要**。先收集 2 周反馈,再决定下一轮迭代做什么。

祝上线顺利!🚀
