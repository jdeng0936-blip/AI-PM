# AI-PM 十大功能 — 技术实现方案

> 遵循 [architecture-rules.md](file:///Users/mac111/Desktop/AI项目管理/agents/rules/architecture-rules.md) + [ai-model-rules.md](file:///Users/mac111/Desktop/AI项目管理/agents/rules/ai-model-rules.md)

---

## 1. 登录认证与安全

### 数据库模型

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,        -- bcrypt 加密
    role VARCHAR(20) NOT NULL DEFAULT 'employee', -- 'admin' | 'employee'
    department VARCHAR(50),                      -- 技术部/生产部/采购部/财务部/商务部/销售部/仓储部
    job_title VARCHAR(50),                       -- 技术部长/研发工程师/仓管 等
    is_active BOOLEAN DEFAULT TRUE,
    must_change_password BOOLEAN DEFAULT TRUE,   -- 首次登录强制改密
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_login_at TIMESTAMPTZ
);

CREATE TABLE audit_logs (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    action VARCHAR(50),    -- 'login' | 'submit_report' | 'change_password'
    ip_address VARCHAR(45),
    detail JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 登录，返回 JWT |
| POST | `/api/auth/change-password` | 修改密码 |
| GET | `/api/auth/me` | 获取当前用户信息 |
| GET | `/api/admin/users` | 总经理获取全员列表 |
| POST | `/api/admin/users` | 总经理创建用户 |

### 核心代码

```python
# backend/app/auth.py
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta

pwd_context = CryptContext(schemes=["bcrypt"])
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
ALGORITHM = "HS256"
TOKEN_EXPIRE_HOURS = 24

def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

# FastAPI 依赖注入
async def get_current_user(token: str = Depends(oauth2_scheme)):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user = await db.get_user(int(payload["sub"]))
    return user

async def require_admin(user = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "仅总经理可访问")
    return user
```

### 前端

- 登录页 → `/login`（公开）
- 路由守卫 → Middleware 校验 JWT，过期自动跳转登录
- localStorage 存储 Token（含 role 信息用于 UI 权限控制）

---

## 2. 催报机制

### 技术方案

使用 **APScheduler** 定时任务（轻量，无需 Celery/Redis 队列）：

```python
# backend/app/scheduler.py
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

# === 定时任务 ===

@scheduler.scheduled_job('cron', hour=17, minute=30)
async def reminder_first():
    """17:30 友好提醒"""
    users = await get_users_not_submitted_today()
    for user in users:
        await send_notification(
            user_id=user.id,
            channel="wecom",
            message=f"Hi {user.username}，今天的日报还没交哦，别忘了～ 😊"
        )

@scheduler.scheduled_job('cron', hour=20, minute=0)
async def reminder_second():
    """20:00 二次催促"""
    users = await get_users_not_submitted_today()
    for user in users:
        await send_notification(
            user_id=user.id,
            channel="wecom",
            message=f"⏰ {user.username}，日报截止时间快到了，请尽快提交！"
        )

@scheduler.scheduled_job('cron', hour=22, minute=0)
async def deadline_mark():
    """22:00 截止，标记未提交 + 通知总经理"""
    users = await get_users_not_submitted_today()
    # 排除请假/出差/节假日
    users = [u for u in users if u.status == 'working']
    if users:
        names = "、".join([u.username for u in users])
        # AI 生成缺勤摘要
        summary = await ai_generate_absence_summary(users)
        await send_notification(
            user_id=ADMIN_USER_ID,
            channel="wecom",
            message=f"📋 今日未提交日报：{names}\n{summary}"
        )

@scheduler.scheduled_job('cron', hour=9, minute=0)
async def consecutive_absence_check():
    """每早 9:00 检查连续未提交"""
    users = await get_consecutive_absent_users(days=2)
    if users:
        await send_notification(
            user_id=ADMIN_USER_ID,
            channel="wecom",
            message=f"🔴 以下人员连续2天未交日报：{'、'.join(...)}"
        )
```

### 数据库查询

```sql
-- 获取今日未提交日报的用户（排除请假）
SELECT u.* FROM users u
LEFT JOIN daily_reports dr
  ON u.id = dr.user_id AND dr.report_date = CURRENT_DATE
LEFT JOIN attendance_status a
  ON u.id = a.user_id AND a.date = CURRENT_DATE
WHERE dr.id IS NULL
  AND u.role = 'employee'
  AND u.is_active = TRUE
  AND COALESCE(a.status, 'working') = 'working';
```

---

## 3. 通知推送渠道

### 统一通知服务

```python
# backend/app/services/notification.py
import httpx

WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK_URL")

async def send_notification(user_id: int, channel: str, message: str):
    """统一通知入口"""
    # 1. 系统内通知（始终写入）
    await db.insert_notification(user_id=user_id, content=message)

    # 2. 外部推送
    if channel == "wecom":
        await _send_wecom(message)
    elif channel == "email":
        await _send_email(user_id, message)

async def _send_wecom(message: str):
    """企微 Webhook 推送"""
    async with httpx.AsyncClient() as client:
        await client.post(WECOM_WEBHOOK, json={
            "msgtype": "text",
            "text": {"content": message}
        })
```

### 数据库模型

```sql
CREATE TABLE notifications (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id),
    content TEXT NOT NULL,
    is_read BOOLEAN DEFAULT FALSE,
    type VARCHAR(20),  -- 'reminder' | 'reject' | 'score' | 'alert'
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/notifications` | 获取当前用户通知列表 |
| PUT | `/api/notifications/{id}/read` | 标记已读 |
| GET | `/api/notifications/unread-count` | 未读数量（前端轮询/WebSocket） |

---

## 4. 岗位日报模板差异

### 设计思路

不是为每个岗位写死不同的表单，而是：
1. 定义**共有字段**（所有人都填的）+ **岗位特有字段**
2. AI 解析时根据岗位自动匹配 Prompt
3. 前端动态渲染表单

### 数据库模型

```sql
CREATE TABLE report_templates (
    id SERIAL PRIMARY KEY,
    job_title VARCHAR(50) UNIQUE NOT NULL,  -- '研发工程师' | '采购经理' | ...
    common_fields JSONB NOT NULL,            -- 共有字段定义
    custom_fields JSONB NOT NULL,            -- 岗位特有字段定义
    ai_prompt_suffix TEXT                    -- 该岗位专用的 Prompt 附加指令
);

-- 示例数据
INSERT INTO report_templates (job_title, common_fields, custom_fields, ai_prompt_suffix)
VALUES ('研发工程师',
    '["today_task", "progress", "blocker", "solution", "tomorrow_plan"]',
    '[
        {"key": "code_version", "label": "代码版本号", "type": "text"},
        {"key": "tech_solution", "label": "技术方案", "type": "textarea"},
        {"key": "test_result", "label": "测试结果", "type": "text"}
    ]',
    '请特别注意提取代码版本号和测试结果。如果提到了分支名或tag，填入code_version。'
);
```

### AI Prompt 适配

```python
# backend/app/services/report_parser.py
async def parse_report(user: User, raw_text: str) -> dict:
    template = await db.get_template(user.job_title)

    system_prompt = f"""
    你是AI项目经理。请将以下员工日报文本解析为JSON。
    该员工岗位：{user.job_title}
    需要提取的共有字段：{template.common_fields}
    需要提取的特有字段：{json.dumps(template.custom_fields, ensure_ascii=False)}
    {template.ai_prompt_suffix or ''}
    输出严格JSON格式。
    """

    response = await client.chat.completions.create(
        model="gemini-2.5-flash",     # 🟢 FAST 场景
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_text}
        ],
        temperature=0.2,
        max_tokens=1024,
    )
    return json.loads(response.choices[0].message.content)
```

### 前端动态表单

```typescript
// 前端根据 template.custom_fields 动态渲染表单
const renderFields = (fields: CustomField[]) => {
  return fields.map(field => {
    switch (field.type) {
      case 'text':    return <Input label={field.label} />
      case 'textarea': return <Textarea label={field.label} />
      case 'number':  return <InputNumber label={field.label} />
    }
  })
}
```

---

## 5. 附件与多媒体支持

### 技术方案

```
用户上传文件 → FastAPI 接收 → 流式传输到阿里云 OSS → 返回 URL → 存入 PostgreSQL
```

### 数据库模型

```sql
CREATE TABLE report_attachments (
    id SERIAL PRIMARY KEY,
    report_id INT REFERENCES daily_reports(id),
    file_type VARCHAR(20),   -- 'image' | 'document' | 'audio'
    file_name VARCHAR(255),
    oss_key VARCHAR(500),    -- OSS 存储路径
    oss_url TEXT,            -- 访问 URL
    file_size INT,
    transcription TEXT,      -- 语音转文字结果（仅 audio 类型）
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/reports/{id}/attachments` | 上传附件 |
| GET | `/api/reports/{id}/attachments` | 获取日报附件列表 |
| DELETE | `/api/attachments/{id}` | 删除附件 |

### 核心代码

```python
# backend/app/services/oss_storage.py
import oss2

auth = oss2.Auth(
    os.getenv("OSS_ACCESS_KEY_ID"),
    os.getenv("OSS_ACCESS_KEY_SECRET")
)
bucket = oss2.Bucket(
    auth,
    os.getenv("OSS_ENDPOINT"),
    os.getenv("OSS_BUCKET_NAME")
)

async def upload_to_oss(file: UploadFile, prefix: str) -> tuple[str, str]:
    """上传文件到 OSS，返回 (oss_key, url)"""
    ext = file.filename.split('.')[-1]
    oss_key = f"{prefix}/{uuid4().hex}.{ext}"
    bucket.put_object(oss_key, file.file)
    url = f"https://{os.getenv('OSS_BUCKET_NAME')}.{os.getenv('OSS_ENDPOINT')}/{oss_key}"
    return oss_key, url

# backend/app/services/asr.py  (语音转文字)
async def transcribe_audio(oss_url: str) -> str:
    """调用讯飞 ASR 转写语音"""
    # 使用讯飞 WebSocket API
    result = await xunfei_asr_client.transcribe(oss_url)
    return result.text
```

### 上传流程

```python
@router.post("/api/reports/{report_id}/attachments")
async def upload_attachment(
    report_id: int,
    file: UploadFile,
    user = Depends(get_current_user)
):
    # 1. 上传到 OSS（不存数据库！遵循 Rule 3）
    oss_key, url = await upload_to_oss(file, f"reports/{report_id}")

    # 2. 语音文件 → 讯飞 ASR 转写
    transcription = None
    file_type = detect_file_type(file.content_type)
    if file_type == "audio":
        transcription = await transcribe_audio(url)

    # 3. 仅存元数据到 PostgreSQL
    attachment = await db.create_attachment(
        report_id=report_id,
        file_type=file_type,
        file_name=file.filename,
        oss_key=oss_key,
        oss_url=url,
        file_size=file.size,
        transcription=transcription
    )
    return attachment
```

---

## 6. 总经理 AI 对话查询

### 设计思路

总经理通过自然语言提问，系统使用 **Tool Calling** 让 LLM 自动选择调用哪个查询函数，而非硬编码 if-else（遵循 Rule 2）。

### 架构

```
总经理提问 → LLM (Tool Calling) → 自动选择工具函数
                                      ├── query_report_stats()   → SQL 聚合
                                      ├── query_project_risk()   → RAG + 风险表
                                      ├── generate_weekly_report() → LLM 撰写
                                      └── query_department_progress() → SQL 筛选
                                   → LLM 汇总回答 → 流式输出给总经理
```

### Tool 定义

```python
# backend/app/services/admin_chat.py
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "query_report_stats",
            "description": "查询日报统计数据：谁延期最多、提交率、平均评分等",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric": {"type": "string", "enum": ["delay_count", "submit_rate", "avg_score"]},
                    "time_range": {"type": "string", "enum": ["today", "this_week", "this_month"]},
                    "department": {"type": "string", "description": "可选，按部门筛选"}
                },
                "required": ["metric", "time_range"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_project_risk",
            "description": "查询项目风险和卡点信息",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "risk_level": {"type": "string", "enum": ["all", "high", "medium"]}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_weekly_report",
            "description": "生成本周管理周报，汇总全员工作",
            "parameters": {
                "type": "object",
                "properties": {
                    "week_offset": {"type": "integer", "description": "0=本周, -1=上周"}
                }
            }
        }
    }
]
```

### API 端点

| 方法 | 路径 | 说明 | 模型 |
|------|------|------|------|
| POST | `/api/admin/chat` | 总经理对话（流式 SSE） | `gemini-3-flash-preview` |
| POST | `/api/admin/chat` (深度分析) | 自动升级到 Pro | `gemini-2.5-pro` |

### 核心代码

```python
@router.post("/api/admin/chat")
async def admin_chat(
    request: ChatRequest,
    user = Depends(require_admin)  # 仅总经理可用
):
    # 第一轮：LLM 决定调用哪个工具
    response = await client.chat.completions.create(
        model="gemini-3-flash-preview",  # 🟡 MEDIUM
        messages=request.messages,
        tools=TOOLS,
        temperature=0.3,
    )

    # 如果 LLM 要调用工具
    if response.choices[0].message.tool_calls:
        tool_call = response.choices[0].message.tool_calls[0]
        func_name = tool_call.function.name
        args = json.loads(tool_call.function.arguments)

        # 执行对应函数获取数据
        result = await execute_tool(func_name, args)

        # 第二轮：LLM 汇总数据生成回答（流式）
        return StreamingResponse(
            stream_with_context(request.messages, tool_call, result),
            media_type="text/event-stream"
        )
```

---

## 7. 历史趋势看板

### 数据库视图（预聚合）

```sql
-- 员工日维度统计视图
CREATE MATERIALIZED VIEW mv_daily_user_stats AS
SELECT
    dr.user_id,
    u.username,
    u.department,
    dr.report_date,
    dr.score,
    dr.pass_check,
    CASE WHEN dr.id IS NOT NULL THEN TRUE ELSE FALSE END AS submitted,
    dr.submitted_at - (dr.report_date + '22:00'::time) AS submit_delay
FROM users u
LEFT JOIN daily_reports dr ON u.id = dr.user_id
WHERE u.is_active = TRUE;

-- 部门周维度汇总视图
CREATE MATERIALIZED VIEW mv_weekly_dept_stats AS
SELECT
    u.department,
    DATE_TRUNC('week', dr.report_date) AS week_start,
    COUNT(dr.id) AS total_reports,
    AVG(dr.score) AS avg_score,
    COUNT(CASE WHEN dr.pass_check THEN 1 END)::FLOAT / NULLIF(COUNT(*), 0) AS pass_rate,
    COUNT(DISTINCT dr.user_id) AS active_users
FROM daily_reports dr
JOIN users u ON dr.user_id = u.id
GROUP BY u.department, DATE_TRUNC('week', dr.report_date);

-- 定时刷新（每日凌晨）
-- scheduler 中添加: REFRESH MATERIALIZED VIEW CONCURRENTLY mv_daily_user_stats;
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/analytics/user-trend?user_id=&days=30` | 个人评分趋势 |
| GET | `/api/analytics/department-compare?period=week` | 部门对比 |
| GET | `/api/analytics/project-health?project_id=` | 项目健康度趋势 |
| GET | `/api/analytics/sprint-efficiency` | Sprint 效率指标 |

### 前端图表（Recharts）

```typescript
// 个人30天评分折线图
<LineChart data={userTrend}>
  <XAxis dataKey="date" />
  <YAxis domain={[0, 100]} />
  <Line dataKey="score" stroke="#8884d8" />
  <ReferenceLine y={kpiTarget} stroke="red" label="KPI目标" />
</LineChart>

// 部门对比柱状图
<BarChart data={deptCompare}>
  <XAxis dataKey="department" />
  <Bar dataKey="avg_score" fill="#82ca9d" />
  <Bar dataKey="submit_rate" fill="#8884d8" />
</BarChart>
```

---

## 8. 数据导出

### 技术方案

| 格式 | 库 | 说明 |
|------|-----|------|
| Excel | `openpyxl` | 支持多 Sheet、样式、图表 |
| PDF | `reportlab` 或 `weasyprint` | 支持中文、表格、页眉页脚 |
| CSV | Python 内置 `csv` | 最轻量 |

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/export/reports?format=xlsx&from=&to=&dept=` | 导出日报 |
| GET | `/api/export/scores?format=pdf&month=` | 导出评分报告 |
| GET | `/api/export/project-summary?format=xlsx&project_id=` | 导出项目摘要 |

### 核心代码

```python
# backend/app/services/export.py
from openpyxl import Workbook
from io import BytesIO

async def export_reports_excel(filters: dict) -> BytesIO:
    reports = await db.query_reports(**filters)

    wb = Workbook()
    ws = wb.active
    ws.title = "日报汇总"

    # 表头
    headers = ["日期", "姓名", "部门", "岗位", "任务", "进度", "卡点", "评分", "AI点评"]
    ws.append(headers)

    # 数据行
    for r in reports:
        ws.append([
            r.report_date.isoformat(), r.username, r.department,
            r.job_title, r.today_task, f"{r.progress}%",
            r.blocker or "无", r.score, r.ai_comment
        ])

    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

@router.get("/api/export/reports")
async def export_reports(
    format: str, from_date: date, to_date: date,
    dept: str = None,
    user = Depends(require_admin)
):
    filters = {"from": from_date, "to": to_date, "department": dept}
    if format == "xlsx":
        buf = await export_reports_excel(filters)
        return StreamingResponse(
            buf,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=reports_{to_date}.xlsx"}
        )
```

---

## 9. KPI 目标设定

### 数据库模型

```sql
CREATE TABLE kpi_targets (
    id SERIAL PRIMARY KEY,
    scope VARCHAR(20) NOT NULL,       -- 'global' | 'department' | 'job_title'
    scope_value VARCHAR(50),          -- NULL=全局, '技术部', '研发工程师' 等
    metric VARCHAR(30) NOT NULL,      -- 'submit_rate' | 'avg_score' | 'sprint_completion' | 'blocker_resolve_days'
    target_value FLOAT NOT NULL,      -- 95.0, 75.0, 80.0, 3.0
    period VARCHAR(10) DEFAULT 'monthly', -- 'weekly' | 'monthly' | 'quarterly'
    created_by INT REFERENCES users(id),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 示例：全局 KPI
INSERT INTO kpi_targets (scope, scope_value, metric, target_value) VALUES
    ('global', NULL, 'submit_rate', 95.0),
    ('global', NULL, 'avg_score', 75.0),
    ('global', NULL, 'blocker_resolve_days', 3.0),
    ('department', '技术部', 'sprint_completion', 80.0);
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/kpi` | 获取所有 KPI 目标 |
| POST | `/api/admin/kpi` | 创建/更新 KPI 目标 |
| GET | `/api/admin/kpi/achievement` | KPI 达成率看板数据 |

### KPI 达成率计算

```python
async def calculate_kpi_achievement(period: str = "monthly") -> list[dict]:
    targets = await db.get_all_kpi_targets()
    results = []
    for t in targets:
        actual = await db.get_actual_metric(t.metric, t.scope, t.scope_value, period)
        results.append({
            "metric": t.metric,
            "scope": f"{t.scope}:{t.scope_value or '全局'}",
            "target": t.target_value,
            "actual": actual,
            "achieved": actual >= t.target_value,
            "gap": round(actual - t.target_value, 1)
        })
    return results
```

---

## 10. 部门与项目分组

### 数据库模型

```sql
-- users 表已有 department 字段（见 #1）

-- 项目组成员关联表
CREATE TABLE project_members (
    id SERIAL PRIMARY KEY,
    project_id INT REFERENCES projects(id),
    user_id INT REFERENCES users(id),
    role VARCHAR(20) DEFAULT 'member', -- 'lead' | 'member'
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, user_id)
);

-- 部门枚举（可扩展）
CREATE TABLE departments (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,  -- '技术部', '生产部', '采购部'...
    manager_id INT REFERENCES users(id)
);
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/admin/reports?group_by=department` | 按部门分组查看日报 |
| GET | `/api/admin/reports?group_by=project&project_id=` | 按项目查看日报 |
| GET | `/api/departments` | 部门列表 |
| GET | `/api/projects/{id}/members` | 项目成员 |

### 前端视图切换

```typescript
// 总经理看板顶部切换器
<Tabs defaultValue="all">
  <Tab value="all">全员</Tab>
  <Tab value="department">按部门</Tab>
  <Tab value="project">按项目</Tab>
</Tabs>

// 按部门分组时：
// GET /api/admin/reports?group_by=department
// 返回: { "技术部": [...], "生产部": [...], "采购部": [...] }
```

---

## 完整实施路线（13 周）

```
=== 关键功能（第1-5周） ===
Phase 1 (第1周):  ① 登录认证     → 没有认证其他都无法开始
Phase 2 (第2周):  ④ 岗位模板     → 日报核心功能依赖模板
Phase 3 (第3周):  ⑤ 附件支持     → 提升日报信息丰富度
Phase 4 (第4周):  ③ 通知推送     → 打通企微/钉钉
Phase 5 (第5周):  ② 催报机制     → 依赖通知渠道先就绪

=== 重要增强（第6-10周） ===
Phase 6 (第6周):  ⑩ 部门分组     → 总经理查看基础能力
Phase 7 (第7周):  ⑨ KPI 目标     → 评分体系锚点
Phase 8 (第8周):  ⑦ 历史趋势     → 数据可视化
Phase 9 (第9周):  ⑧ 数据导出     → Excel/PDF 汇报
Phase 10(第10周): ⑥ AI 对话查询  → Tool Calling

=== 战略增强（第11-13周） ===
Phase 11(第11周): ⑪ OKR 战略对齐  → 目标管理基础设施
Phase 12(第12周): ⑫ 资源负载预判  → 故事点负载池 + 水位可视化
Phase 13(第13周): ⑬ AI 自动复盘   → 知识资产沉淀（依赖前面所有数据积累）
```

---

## 11. OKR 战略对齐

### 数据库模型

```sql
CREATE TABLE okr_cycles (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,             -- '2026 Q1', '2026 H1'
    period VARCHAR(20) NOT NULL,            -- 'quarterly' | 'half_yearly'
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    created_by INT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE objectives (
    id SERIAL PRIMARY KEY,
    cycle_id INT REFERENCES okr_cycles(id),
    title TEXT NOT NULL,                     -- '206样机具备行业参展能力'
    owner_id INT REFERENCES users(id),       -- 负责人（总经理或部门负责人）
    progress FLOAT DEFAULT 0,                -- 0-100，由 KR 自动计算
    status VARCHAR(20) DEFAULT 'on_track',   -- 'on_track' | 'at_risk' | 'behind'
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE key_results (
    id SERIAL PRIMARY KEY,
    objective_id INT REFERENCES objectives(id),
    title TEXT NOT NULL,                      -- '大模型推理延迟降低至500ms内'
    metric_type VARCHAR(20),                  -- 'number' | 'percentage' | 'boolean'
    target_value FLOAT,                       -- 500 (ms)
    current_value FLOAT DEFAULT 0,            -- AI 从日报自动更新
    unit VARCHAR(20),                         -- 'ms' | '%' | '个'
    progress FLOAT DEFAULT 0,
    owner_id INT REFERENCES users(id)
);

CREATE TABLE kr_task_links (
    id SERIAL PRIMARY KEY,
    kr_id INT REFERENCES key_results(id),
    task_id INT REFERENCES tasks(id),         -- Sprint任务绑定KR
    contribution_weight FLOAT DEFAULT 1.0     -- 该任务对KR的贡献权重
);

CREATE TABLE kr_progress_logs (
    id SERIAL PRIMARY KEY,
    kr_id INT REFERENCES key_results(id),
    report_id INT REFERENCES daily_reports(id),
    previous_value FLOAT,
    new_value FLOAT,
    ai_extracted BOOLEAN DEFAULT TRUE,        -- AI从日报自动提取
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### AI 自动更新 KR 进度

```python
async def auto_update_kr_from_report(report: DailyReport):
    """日报入库后，AI 自动检测是否更新了某个 KR 的进度"""
    linked_krs = await db.get_krs_linked_to_user_tasks(report.user_id)
    if not linked_krs:
        return

    prompt = f"""
    以下是员工日报内容：{report.raw_text}
    该员工当前关联的 KR：{json.dumps([kr.dict() for kr in linked_krs])}
    请判断日报中是否包含某个 KR 的进度更新数据，返回 JSON：
    [{{"kr_id": 1, "new_value": 450, "reason": "推理延迟从800ms降至450ms"}}]
    如果没有进度更新，返回空数组 []
    """
    response = await client.chat.completions.create(
        model="gemini-2.5-flash",  # 🟢 FAST 场景
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2, max_tokens=1024,
    )
    updates = json.loads(response.choices[0].message.content)
    for u in updates:
        await db.update_kr_progress(u["kr_id"], u["new_value"], report.id)
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/okr/cycles` | OKR 周期列表 |
| POST | `/api/admin/okr/objectives` | 创建 Objective |
| POST | `/api/admin/okr/key-results` | 创建 KR |
| POST | `/api/okr/link-task` | 绑定任务到 KR |
| GET | `/api/okr/dashboard` | OKR 进度仪表盘 |

---

## 12. 资源负载水位与瓶颈预判

### 数据库模型

```sql
-- tasks 表增加故事点字段
ALTER TABLE tasks ADD COLUMN story_points INT DEFAULT 0;

-- 成员产能基线
CREATE TABLE capacity_baselines (
    id SERIAL PRIMARY KEY,
    user_id INT REFERENCES users(id) UNIQUE,
    points_per_sprint INT DEFAULT 20,        -- 正常负荷基线
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
```

### 负载水位计算

```python
async def calculate_workload(sprint_id: int) -> list[dict]:
    members = await db.get_sprint_members(sprint_id)
    results = []
    for m in members:
        assigned = await db.get_assigned_points(m.user_id, sprint_id)
        baseline = await db.get_capacity_baseline(m.user_id)

        # 跨项目总负载
        cross_project = await db.get_cross_project_points(m.user_id, sprint_id)

        load_pct = (assigned / baseline.points_per_sprint) * 100
        results.append({
            "user": m.username,
            "assigned_points": assigned,
            "baseline": baseline.points_per_sprint,
            "load_percentage": round(load_pct),
            "cross_project_total": cross_project,
            "status": "overloaded" if load_pct > 150
                      else "full" if load_pct > 100
                      else "normal"
        })
    return results

# Sprint 规划时自动检查
async def check_sprint_feasibility(sprint_id: int):
    workloads = await calculate_workload(sprint_id)
    overloaded = [w for w in workloads if w["status"] == "overloaded"]
    if overloaded:
        advice = await client.chat.completions.create(
            model="gemini-3-flash-preview",  # 🟡 MEDIUM
            messages=[{
                "role": "user",
                "content": f"以下成员过载：{json.dumps(overloaded)}，请建议调配方案"
            }],
            temperature=0.5, max_tokens=2048,
        )
        await send_notification(ADMIN_USER_ID, "wecom", advice)
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/capacity/sprint/{id}` | Sprint 负载水位 |
| GET | `/api/capacity/overview` | 全员水位概览 |
| POST | `/api/admin/capacity/baseline` | 设置产能基线 |
| GET | `/api/capacity/conflicts` | 跨项目冲突检测 |

---

## 13. AI 驱动自动化复盘

### 核心代码

```python
async def generate_retrospective(scope: str, scope_id: int) -> dict:
    """
    scope: 'sprint' | 'milestone' | 'project'
    自动生成阶段复盘报告
    """
    # 1. 收集该阶段全部数据
    reports = await db.get_reports_in_scope(scope, scope_id)
    blockers = await db.get_blockers_in_scope(scope, scope_id)
    scores = await db.get_scores_in_scope(scope, scope_id)
    workloads = await db.get_workloads_in_scope(scope, scope_id)

    context = f"""
    日报数量: {len(reports)}
    卡点记录: {json.dumps(blockers, ensure_ascii=False)}
    评分统计: 平均{scores['avg']}, 最低{scores['min']}, 最高{scores['max']}
    负载情况: {json.dumps(workloads, ensure_ascii=False)}
    """

    # 2. LLM 生成复盘报告
    response = await client.chat.completions.create(
        model="gemini-2.5-pro",  # 🔴 HEAVY 场景
        messages=[{
            "role": "system",
            "content": """你是项目复盘分析师。请基于以下数据生成结构化复盘报告，包含：
            1. 📊 关键数据摘要
            2. 🔥 卡点热力图（哪个环节踩坑最多）
            3. ⚡ 效率瓶颈分析
            4. 💡 改进建议（具体可执行）
            5. ⭐ 最佳实践提炼
            输出 JSON 格式。"""
        }, {
            "role": "user", "content": context
        }],
        temperature=0.5, max_tokens=4096,
    )
    report = json.loads(response.choices[0].message.content)

    # 3. 自动沉淀知识资产
    await save_to_knowledge_base(report["best_practices"], type="practice")
    await save_to_knowledge_base(report["improvement_suggestions"], type="faq")

    return report
```

### 数据库模型

```sql
CREATE TABLE retrospective_reports (
    id SERIAL PRIMARY KEY,
    scope VARCHAR(20) NOT NULL,       -- 'sprint' | 'milestone' | 'project'
    scope_id INT NOT NULL,
    report_content JSONB NOT NULL,     -- AI 生成的完整报告
    generated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE knowledge_assets (
    id SERIAL PRIMARY KEY,
    type VARCHAR(20) NOT NULL,        -- 'faq' | 'risk_playbook' | 'best_practice'
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    source_retro_id INT REFERENCES retrospective_reports(id),
    tags JSONB,                       -- ['电源选型', '供应商', '采购']
    embedding Vector(1536),           -- pgvector，支持语义检索
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/retro/generate` | 触发生成复盘报告 |
| GET | `/api/retro/{scope}/{id}` | 查看复盘报告 |
| GET | `/api/knowledge/search?q=` | 语义搜索知识资产 |
| GET | `/api/knowledge/recommend?blocker=` | AI 推荐相似问题解决方案 |

