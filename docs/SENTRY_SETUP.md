# Sentry 错误监控接入指南

> Stage 4 引入。Backend 已完成代码集成(DSN 缺失时自动跳过),Frontend 需手工启用。

---

## 一、为什么用 Sentry

V2.0 上线后,生产环境的错误只能靠 `journalctl` / 日志聚合发现 — 信号慢、上下文缺。
Sentry 提供:
- 实时错误捕获 + 完整 stack trace
- 用户身份、请求路径、SQL 查询等上下文
- 错误聚合去重 + 趋势追踪
- 接通 Slack / 邮件 / 钉钉告警(免费层够用)

---

## 二、Backend 接入(已完成)

### 2.1 已就位

- `requirements.txt` 添加 `sentry-sdk[fastapi]>=2.13.0`
- `app/config.py` 新增 3 个字段:`sentry_dsn`、`sentry_traces_sample_rate`、`sentry_environment`
- `app/main.py` 在 FastAPI app 创建之前 init Sentry(env-driven,DSN 留空则跳过)

### 2.2 你需要做的:获取 DSN

1. 登录 [sentry.io](https://sentry.io/) → Create Project
2. Platform 选 **Python → FastAPI**
3. 取得 DSN,形如:
   ```
   https://xxxxxxxx@oxxxx.ingest.sentry.io/yyyyyyy
   ```

### 2.3 配置 `.env`

```bash
SENTRY_DSN=https://xxxxxxxx@oxxxx.ingest.sentry.io/yyyyyyy
SENTRY_TRACES_SAMPLE_RATE=0.1    # 性能采样率:dev=1.0,prod=0.1(10%)
SENTRY_ENVIRONMENT=prod          # dev / staging / prod
```

### 2.4 验证

启动 backend,日志应出现:
```
🛰️  Sentry 已启用 env=prod traces_sample_rate=0.1
```

然后人为触发一个错误:
```bash
curl http://127.0.0.1:8000/api/v1/__sentry_test__   # 该路由暂未实现,故意 404
# 或在某个测试 endpoint 中 raise RuntimeError("sentry smoke test")
```

去 Sentry Issues 页面,几秒内应能看到这条 error 附带完整 stack。

---

## 三、Frontend 接入(待手工启用)

> 未在代码中集成的原因:`@sentry/nextjs` 体积较大,且需要 source map 上传配置;
> CI 在依赖缺失时会因 TS 报错而失败。所以留给运维统一配置。

### 3.1 安装依赖

```bash
cd frontend
npm install --save @sentry/nextjs
```

### 3.2 运行 Sentry 配置向导

```bash
npx @sentry/wizard@latest -i nextjs
```

向导会:
- 让你登录 Sentry 账号
- 选择 project
- 自动生成 `sentry.client.config.ts` / `sentry.server.config.ts` / `sentry.edge.config.ts`
- 修改 `next.config.js` 注入 Sentry webpack plugin
- 在 `.env.local` 写入 `SENTRY_AUTH_TOKEN`(用于上传 source map)

### 3.3 在 `.env.production` 配置

```bash
NEXT_PUBLIC_SENTRY_DSN=https://aaaaaaaaaa@oxxxx.ingest.sentry.io/zzzzzz
SENTRY_AUTH_TOKEN=sntrys_xxxxxxxx     # CI build 时上传 source map 用
SENTRY_ORG=your-org
SENTRY_PROJECT=ai-pm-frontend
```

注意:**`NEXT_PUBLIC_*` 会被打进客户端 bundle,可被任何访客读到** — DSN 是 public 的,无所谓。但 `SENTRY_AUTH_TOKEN` 是 secret,只能在 CI / 服务端 env 出现。

### 3.4 验证

```typescript
// 在任意 page 临时加,看 Sentry 是否能捕获
'use client'
import { useEffect } from 'react'
export default function TestPage() {
  useEffect(() => {
    throw new Error("sentry frontend smoke test")
  }, [])
  return <div>testing...</div>
}
```

---

## 四、生产环境部署清单

- [ ] Backend `.env` 配置 `SENTRY_DSN` 后**重启 uvicorn**
- [ ] Frontend `npm run build` 时 `SENTRY_AUTH_TOKEN` 必须可见(用于 source map 上传)
- [ ] Sentry 项目设置告警规则:
  - 新 issue → Slack 或邮件
  - 错误率超阈值(如 5 分钟内 >50 条)→ 升级告警
- [ ] PII 合规:
  - Backend `send_default_pii=False`(已默认)
  - Frontend 在 wizard 生成的 config 里同样关闭
- [ ] 性能采样率:
  - dev / staging:1.0(全采样,方便调试)
  - prod:0.1(10%,控制配额)
- [ ] 接通公司 SSO(如有)

---

## 五、相关文件

- `backend/app/main.py` — 第 14-39 行,Sentry init 块
- `backend/app/config.py` — 第 146-156 行,Sentry settings 字段
- `backend/requirements.txt` — `sentry-sdk[fastapi]>=2.13.0`
- `backend/.env.example` — 第 X 行,SENTRY_DSN 等占位说明
