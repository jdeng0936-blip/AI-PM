# AI-PM 应急预案 Playbook

> Stage 2 必备。"上线后不回滚"模式下,每一类故障都需要可执行的 SOP。
> 凌晨 2 点 oncall 不应该再去现编流程。

---

## 0. 总原则

1. **先止血,后定位**:用户可见的服务先恢复,再找根因
2. **不要慌着 `docker compose down`**:那会破坏当前状态线索 — 先 `docker logs / docker exec` 取证
3. **任何 SQL 改生产 DB 之前先备份**:`bash scripts/backup.sh && wait`
4. **每次紧急操作都开 oncall 临时频道**:即时记录每条命令 + 结果,事后 retro

---

## 1. P0:服务完全不可用(用户报"打不开")

### 1.1 5 分钟止血流程

```bash
# Step 1:确认是不是只有自己打不开
curl -I https://aipm.your-domain.com/health
# 200 → 只是用户本地问题,联系用户排查网络
# 5xx / timeout → 真的挂了,继续

# Step 2:看容器状态
docker ps --filter "name=aipm-" --format 'table {{.Names}}\t{{.Status}}'
# 期望所有 4-5 个容器是 Up
# 如果有 Exited → 看 docker logs <name> --tail 50

# Step 3:看 /health/detailed
curl https://aipm.your-domain.com/health/detailed | python3 -m json.tool
# 哪个 check 失败哪个先排查(DB / Redis / Scheduler)

# Step 4:看资源
df -h     # 磁盘满了?(/var/lib/docker 是大头)
free -h   # 内存满了?
docker stats --no-stream
```

### 1.2 常见症状 → 处置

| 症状 | 大概率原因 | 处置 |
|---|---|---|
| 所有容器 `Exited` | OOM-kill 或 reboot | `docker compose -f docker-compose.prod.yml -f docker-compose.prod.https.yml up -d`(自动重启) |
| `aipm-backend Restarting...` | 启动报错,看 logs | `docker logs aipm-backend --tail 80` |
| Caddy 502 | backend 挂或 health 没过 | 先恢复 backend |
| DNS 超时 | 解析问题 | `dig aipm.your-domain.com`,看是不是 DNS provider 挂了 |
| `/health/detailed` redis.ok=false | Redis 挂 | `docker restart aipm-redis`;分布式锁自动降级,业务不中断 |
| 磁盘满 | pgdata / docker logs 涨太多 | `docker system prune -af --volumes` ⚠️ 谨慎(volume 别误删 pgdata) |

---

## 2. P1:部分功能异常(用户报"AI 不回复 / 日报评分不出来")

### 2.1 LLM 调用失败

```bash
# 看 backend 日志里 LiteLLM / ai_engine 报错
docker logs aipm-backend --tail 200 2>&1 | grep -iE "litellm|ai_engine|gemini" | tail -30

# 常见原因:
# - LITELLM_API_KEY 配额耗尽 → 看 .env DAILY_TOKEN_LIMIT,看 Langfuse usage
# - LiteLLM 网关挂了 → curl 一下 LITELLM_BASE_URL/health
# - 模型本身限流 → 等 1 分钟重试,或切到备份 model
```

**临时止血**:在 `backend/llm_registry.yaml` 里切到备份模型,然后 `docker restart aipm-backend`。

### 2.2 通知发不出来

```bash
# 看是哪个渠道挂
docker exec aipm-postgres psql -U aipm -d aipm_db -c "
  SELECT channel, status, count(*) FROM notifications
  WHERE created_at > now() - interval '1 hour'
  GROUP BY channel, status ORDER BY 1, 2;
"

# wechat / dingtalk status=failed → 看 retry_count + 最近一条 detail
# 通常是 webhook 被群删除 / token 过期 → 重新配 .env 然后 docker restart
```

### 2.3 APScheduler 不触发

```bash
# 1. 看启动日志,任务数应该 = 11
docker logs aipm-backend 2>&1 | grep "APScheduler 已启动"

# 2. /health/detailed 看 scheduler.running=true
curl https://aipm.your-domain.com/health/detailed | grep scheduler -A3

# 3. 看 Redis 锁有没有卡住(理论上有 TTL 自动过期)
docker exec aipm-redis redis-cli KEYS 'aipm:scheduler:lock:*'
# 如果有过期未清理的 key,删掉:
# docker exec aipm-redis redis-cli DEL aipm:scheduler:lock:<name>
```

---

## 3. 数据故障

### 3.1 数据库连接拒绝

```bash
docker logs aipm-postgres --tail 50
docker exec aipm-postgres pg_isready -U aipm

# 如果是 max_connections 满了:
docker exec aipm-postgres psql -U aipm -d aipm_db -c "
  SELECT count(*), state FROM pg_stat_activity GROUP BY state;
"
# 太多 idle in transaction → 应用层连接泄漏,docker restart aipm-backend 短期解决
```

### 3.2 数据丢失 / 损坏(P0)

```bash
# 立即停写(防止覆盖最新可用状态)
docker stop aipm-backend

# 找最新一份完好备份
ls -lt /opt/aipm/backend/backups/*.sql.gz | head -5

# 用 restore_drill.sh 先在演练库验证备份可用
cd /opt/aipm/backend
bash scripts/restore_drill.sh
# 看到 "🎉 备份恢复演练全部通过" 才能继续

# 真正恢复到生产 DB(⚠️ 不可逆)
# 1. 备份当前损坏库(取证用)
docker exec aipm-postgres pg_dump -U aipm aipm_db | gzip > /tmp/corrupted_$(date +%s).sql.gz

# 2. drop + 恢复
docker exec aipm-postgres psql -U aipm -d postgres -c "DROP DATABASE aipm_db;"
docker exec aipm-postgres psql -U aipm -d postgres -c "CREATE DATABASE aipm_db OWNER aipm;"
gunzip -c /opt/aipm/backend/backups/<最新备份>.sql.gz | docker exec -i aipm-postgres psql -U aipm -d aipm_db

# 3. 验 schema 一致
docker exec aipm-backend alembic check

# 4. 重启业务
docker start aipm-backend
curl https://aipm.your-domain.com/health/detailed
```

---

## 4. 紧急 bug 修复 SOP

### 4.1 发现 → 部署的流程

```bash
# 1. 本地新分支
git checkout -b hotfix/<short-desc>

# 2. 修代码,本地跑测试
cd backend && .venv/bin/pytest tests/ --ignore=tests/test_e2e_ipd.py -q

# 3. push 触发 CI(必须全绿才能继续)
git push origin hotfix/<short-desc>
# 在 GH 看 CI 跑完

# 4. 合到 main
git checkout main && git merge --no-ff hotfix/<short-desc>
git push origin main

# 5. 生产部署
ssh aipm-prod
cd /opt/aipm
git pull
docker compose -f docker-compose.prod.yml -f docker-compose.prod.https.yml up -d --build backend  # 单独重建 backend
# 如果改了 schema → docker exec aipm-backend alembic upgrade head

# 6. 验证
curl https://aipm.your-domain.com/health/detailed
# 复现一次原 bug,确认已修复
```

**整个流程 ≤ 2 小时**(CI 占大头 ~5 分钟,人是瓶颈)。

### 4.2 不能等 CI 的极端情况

如果 CI 跑不通(GitHub Actions 故障)或者 ≤ 30 分钟必须修复:

1. **冻结策略**:停掉 APScheduler、只保留只读接口
2. **直接生产改 + 立即开 oncall record**
3. 改完立刻补一个 PR + tag,标记 `emergency-bypass-ci`,事后 retro

⚠️ **永远不要绕过 `alembic check`**。schema 漂移是慢性病,绕了今天明天会暴雷。

---

## 5. 回滚 SOP("上线后不回滚"是默认,但极端情况下需要)

```bash
# 找到上一个 stable tag
git tag --list 'v*' | sort -V | tail -3
# 假设 v2.0.0 是上一个

cd /opt/aipm
git checkout v2.0.0

# ⚠️ 关键:V2.x → V2.(x-1) 如果跨了 alembic migration,要先 downgrade
docker exec aipm-backend alembic current
docker exec aipm-backend alembic downgrade <previous_rev_id>

# 重新部署
docker compose -f docker-compose.prod.yml -f docker-compose.prod.https.yml up -d --build

# 验证
curl https://aipm.your-domain.com/health/detailed
```

**风险提示**:downgrade 经常**有数据损失风险**(新增列被删 = 该列数据没了)。除非 V2.x 引入了不可恢复的损坏,否则**修向前 (hotfix) 永远优于回滚**。

---

## 6. 联系人 / 升级链路

| 角色 | 谁 | 何时呼 |
|---|---|---|
| oncall 一线 | 待定 | 任何 P0/P1 |
| 后端 owner | 待定 | LLM / API / DB 故障 |
| 前端 owner | 待定 | 页面打不开 / 渲染错 |
| 基础设施 | 待定 | 公有云 / DNS / 证书 |
| 业务 owner | 待定 | 决策"是否对用户公开通知" |

⚠️ 上线第一周前必须把待定填完。
