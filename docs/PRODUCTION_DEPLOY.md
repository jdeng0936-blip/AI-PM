# AI-PM V2.1 公网生产部署 SOP

> 适用范围:把 V2.1 部署到**公有云 ECS / 容器服务**,对外提供 HTTPS 访问。
> 与之相对的是 `DEPLOY.md`(单机内网快速部署,无 HTTPS)。
>
> **目标用户**:运维 / 开发负责人。
> **上线模式**:Phase 2.0 配套 "真实生产 + 上线后不回滚"。

---

## 一、上线前 checklist(必须全 ✅ 才能继续)

### 1.1 基础设施
- [ ] **公有云 ECS 实例已开通**(阿里云 / 腾讯云),最低规格 4 vCPU / 8 GB RAM / 100 GB SSD
- [ ] **公网 IP 已绑定**,80 / 443 端口在安全组放行(其它端口全部关闭)
- [ ] **域名解析**:`aipm.your-domain.com` A 记录指向 ECS 公网 IP
- [ ] **SSH 密钥认证已配**(关闭密码登录,只允许 key)
- [ ] **服务器时区**:`timedatectl set-timezone Asia/Shanghai`(否则定时任务时间会错)

### 1.2 软件依赖
- [ ] Docker ≥ 24.x + Docker Compose v2.20+(`docker compose version` 测一下)
- [ ] PostgreSQL 客户端工具:`apt install postgresql-client-16`(备份脚本用)
- [ ] 可选:`ossutil`(如果 .env 配 `BACKUP_OSS_BUCKET`,需要把备份上传 OSS)

### 1.3 凭证就位
- [ ] **Sentry 两个 DSN**:backend (Python/FastAPI 项目) + frontend (React 项目)
- [ ] **LiteLLM API Key**(代码默认走 LiteLLM 网关)
- [ ] **企微 / 钉钉 webhook**(否则 notification 走 skipped)
- [ ] **OSS 凭证**(附件 + ASR 用,公网不能依赖 LocalFile)
- [ ] **JWT_SECRET_KEY**:`openssl rand -hex 32` 生成

---

## 二、首次部署流程

### Step 1:服务器准备
```bash
# 在 ECS 上以非 root 用户(假设 aipm-user)操作
sudo mkdir -p /opt/aipm
sudo chown $(whoami):$(whoami) /opt/aipm
cd /opt/aipm
git clone https://github.com/jdeng0936-blip/AI-PM.git .
git checkout main      # 或具体 tag,如 v2.1.0
```

### Step 2:写 .env(关键!)
```bash
cd backend
cp .env.production.template .env

# ⚠️ 标 ⚠️ 的字段全部必须改:
#   - POSTGRES_PASSWORD(强密码)
#   - DATABASE_URL(密码同步)
#   - JWT_SECRET_KEY(openssl rand -hex 32)
#   - WECHAT_* / DINGTALK_* / OSS_* / LITELLM_*
#   - SENTRY_DSN + NEXT_PUBLIC_SENTRY_DSN
#   - CORS_ALLOWED_ORIGINS=["https://aipm.your-domain.com"]
nano .env

# 验证 .env 没有占位符残留(否则 preflight 会拦截)
grep -E "⚠️|YOUR_|change-me" .env && echo "❌ 还有占位符" || echo "✅ 干净"
```

### Step 3:跑预检脚本
```bash
cd /opt/aipm/backend
bash scripts/preflight.sh    # 看 .env 完整性、Docker 版本、磁盘空间
```

### Step 4:HTTPS 部署
```bash
cd /opt/aipm

# 设置生产域名(导出到 shell + 写到 systemd / .bashrc 永久化)
export AIPM_DOMAIN=aipm.your-domain.com

# 启动:postgres + redis + backend + frontend + caddy(自动 Let's Encrypt)
docker compose -f docker-compose.prod.yml -f docker-compose.prod.https.yml up -d --build

# 看 Caddy 拿证书的过程(15-60 秒)
docker logs -f aipm-caddy
# 看到 "certificate obtained successfully" 即成功
```

### Step 5:数据库迁移(关键!)
```bash
cd /opt/aipm/backend
docker exec aipm-backend alembic upgrade head
# 应该输出 6 个 revision 顺序跑通到 head=d2c623c6291a (或更新)

docker exec aipm-backend alembic check
# 期望:No new upgrade operations detected
```

### Step 6:创建第一个 admin
```bash
docker exec -it aipm-backend python scripts/seed_admin.py
# 按提示输入手机号、姓名、密码;脚本会用 bcrypt hash 入库
```

### Step 7:验证 HTTPS 上线
```bash
# 从本机访问
curl https://aipm.your-domain.com/health
# 期望:{"status":"ok","service":"huiyuancheng-ai-pm"}

# 多维度详细检查
curl https://aipm.your-domain.com/health/detailed | python3 -m json.tool
# 期望:status=ok,checks.database.ok=true,checks.redis.ok=true,
#       checks.sentry.enabled=true,checks.scheduler.running=true,job_count=11
```

### Step 8:确认 APScheduler 11 个任务全部注册
```bash
docker logs aipm-backend 2>&1 | grep -i "APScheduler 已启动"
# 期望:"⏰ APScheduler 已启动,注册了 11 个定时任务"
```

### Step 9:Sentry 接收第一条事件
```bash
# 故意触发一个测试错误(POST 一个会被拒绝的请求)
curl -X POST https://aipm.your-domain.com/api/v1/__nonexistent__
# 等几秒,去 Sentry web 看是否有 issue
```

---

## 三、配 crontab(运维自动化)

```bash
crontab -e
```

加入:
```cron
# 每日 03:00 数据库备份
0 3 * * * cd /opt/aipm/backend && bash scripts/backup.sh >> /var/log/aipm-backup.log 2>&1

# 每周一 04:00 备份恢复演练(没演练过的备份不算备份)
0 4 * * 1 cd /opt/aipm/backend && bash scripts/restore_drill.sh >> /var/log/aipm-restore-drill.log 2>&1
```

`crontab -l` 确认两行已添加。

---

## 四、上线后第一周观察

每天早上检查一次:

```bash
# 1. /health/detailed 全绿
curl https://aipm.your-domain.com/health/detailed | python3 -m json.tool

# 2. Sentry P0/P1 issue 数(>0 立即响应)
#    去 Sentry web → 项目 → Issues 看 24h 趋势

# 3. 数据库行数增长合理
docker exec aipm-postgres psql -U aipm -d aipm_db -c "SELECT
  (SELECT count(*) FROM users) AS users,
  (SELECT count(*) FROM daily_reports) AS reports_total,
  (SELECT count(*) FROM daily_reports WHERE created_at > now() - interval '24h') AS reports_24h,
  (SELECT count(*) FROM audit_logs) AS audit_logs;
"

# 4. APScheduler 触发记录
docker logs aipm-backend --since 24h 2>&1 | grep "⏰" | tail -20
# 期望:看到 17:30 催报、09:00 晨报、22:00 截止等真实触发条目

# 5. 备份文件存在
ls -lh /opt/aipm/backend/backups/ | tail -5
```

---

## 五、下次升级(后续 V2.x)

```bash
cd /opt/aipm
git pull origin main
docker compose -f docker-compose.prod.yml -f docker-compose.prod.https.yml up -d --build
docker exec aipm-backend alembic upgrade head
docker exec aipm-backend alembic check
curl https://aipm.your-domain.com/health/detailed | python3 -m json.tool
```

---

## 六、相关文档

- `DEPLOY.md` — 单机/内网快速部署(无 HTTPS)
- `docs/INCIDENT_PLAYBOOK.md` — 应急预案(回滚 / 数据恢复 / bug 修复)
- `docs/MIGRATION_GUIDE.md` — Alembic 迁移规范
- `docs/SENTRY_SETUP.md` — Sentry 接入步骤
- `docs/RELEASE_NOTES_V2.0.md` — V2.0 发版说明
