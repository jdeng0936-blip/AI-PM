# SPEC.md — ERP 联动网关 v2 需求规约 (可证伪)

## 1. 目标与背景 (Goal)
AI-PM 项目中，`RiskAlert` (全局卡点表) 记录了由日报 AI 抽取的各类项目进度阻塞卡点。现有的 ERP 联动网关（`backend/app/routers/erp.py`）MVP 版本存在重大设计缺陷：
- **安全漏洞**：直接绑定了 `UserRole.admin`，外部 stateless 的 ERP 无法通过常规 Session/JWT 鉴权。
- **误伤风险**：仅采用 description 模糊匹配。若日报中记录 "MCU模块采购延迟"（硬件卡点）与 "MCU模块软件烧录失败"（软件卡点），模糊匹配 "MCU模块" 会将软件卡点一并错误解除。
- **孤岛操作**：卡点更新后没有触发健康度引擎（`health_engine.py`）重算，也没有发出微信群通知，且缺乏审计留痕。

本 SPEC 旨在将网关升级为 **ERP 联动网关 v2 (闭环增强版)**，实现具有 HMAC 鉴权、精确匹配优先的双轨匹配、实时健康度刷新与消息推送的闭环网关。

---

## 2. 核心需求与可证伪指标 (Requirements)

### R1. HMAC-SHA256 签名鉴权 (可证伪)
- **输入要求**：请求头必须携带 `X-ERP-Signature`，其值为使用 `ERP_WEBHOOK_SECRET` 作为密钥，对 HTTP Request Body 计算得出的 HMAC-SHA256 十六进制摘要。
- **安全拦截**：若 Header 缺失或签名不匹配，接口必须返回 `401 Unauthorized`。
- **兼容测试模式**：若系统环境变量/配置中未设置 `ERP_WEBHOOK_SECRET`（或为空），为保障本地开发体验，应记录 Warning 日志并自动跳过鉴权校验。
- **【证伪指标】**：使用不正确的签名或空签名请求时，接口必须 100% 拒绝并返回 401。

### R2. 数据库模型扩展 (向后兼容)
- **表结构变更**：在 `risk_alerts` 表中新增两个字段：
  - `material_code`: `String(64)`, 允许为空 (`nullable=True`), 加索引 (`index=True`)。
  - `po_number`: `String(64)`, 允许为空 (`nullable=True`), 加索引 (`index=True`)。
- **向后兼容性**：历史预警记录无需回填，上述字段默认为空。

### R3. 双轨精确匹配匹配逻辑 (可证伪)
当 ERP 发送物料状态更新消息时，匹配策略如下：
1. **精确匹配优先**：
   - 若 payload 中包含 `po_number`，且 `RiskAlert` 中存在 `po_number` 匹配的记录，则优先精准解除。
   - 若 payload 中包含 `material_code`，且 `RiskAlert` 中存在 `material_code` 匹配的记录，则精准解除。
2. **模糊模糊回退**：
   - 仅当无法根据 `po_number` 或 `material_code` 精确找到任何记录时，回退到在 `description` 中利用 `payload.material` 进行 `ilike` 模糊匹配。
- **【证伪指标】**：创建包含 "MCU模块软件烧录失败" 模糊卡点，以及一个带有 `material_code="M-MCU-001"` 的硬件卡点。ERP 接口发送 `material_code="M-MCU-001"` 状态更新后，只有硬件卡点被解除，软件卡点保持 `unresolved`。

### R4. 闭环联动重算与实时通知 (可证伪)
- **健康度重算**：接口解除相关 `RiskAlert` 记录后，必须提取该 `RiskAlert` 对应用户的 `user_id`，在 `project_members` 中查询该用户关联的处于 `active` 状态的项目 `project_id`。
- **触发重算**：对查询到的每个项目，同步或异步调用 `health_engine.refresh_project_health(db, project_id)` 进行健康度刷新。
- **微信推送通知**：通过 `notification_service.py` 触发微信群机器人通知。
  - 新增通知模板 `NotificationTemplate.erp_resolved = "erp_resolved"`。
  - 企微群机器人接收的消息格式与渲染效果需包含：物料名称、状态、单据号、备注、以及本次解除的卡点数量。
- **【证伪指标】**：解除卡点后，项目的 `health_status` 从 red 自动变为 green/yellow，并且在企微机器人的模拟调用中产生对应格式 of Markdown 数据包。

---

## 3. 接口协议契约 (Interface Contract)

### POST `/api/v1/erp/webhook/status_update`

#### 请求 Header
```http
Content-Type: application/json
X-ERP-Signature: 8f9a2b7c4d5e... (HMAC-SHA256 十六进制串)
```

#### 请求 Payload
```json
{
  "material": "智能控制MCU模块",
  "material_code": "M-MCU-001",
  "po_number": "PO-2026-0089",
  "status": "已入库",
  "erp_order_no": "ERP-IN-99882",
  "remark": "今日下午由顺丰送达并完成检验入库"
}
```

#### 响应 Payload (成功 200 OK)
```json
{
  "success": true,
  "material": "智能控制MCU模块",
  "material_code": "M-MCU-001",
  "po_number": "PO-2026-0089",
  "erp_status": "open",
  "resolved_alerts_count": 1,
  "resolved_alert_ids": ["3963b35c-2049-449e-b079-bc8f6d68f9ef"]
}
```

---

## 4. 验收标准与测试矩阵 (Acceptance Criteria)

| 编号 | 测试用例描述 | 预期结果 |
|---|---|---|
| TC-01 | 签名未配置时直接调用接口 | 鉴权自动跳过，依据 Payload 正常执行匹配并解除卡点，状态为 200 |
| TC-02 | 配置了签名密钥，使用空 `X-ERP-Signature` 或伪造的签名请求 | 接口直接拦截并返回 `401 Unauthorized` |
| TC-03 | 精确匹配优先测试（带 `material_code`） | 仅解除该 code 对应的卡点，名称相似但不带该 code 的卡点不受影响 |
| TC-04 | 模糊回退测试（不带 `material_code`） | 回退到对 `description` 字段进行 ilike 模糊查询，正确解除匹配的卡点 |
| TC-05 | 联动刷新测试 | `projects.health_score` 和 `projects.health_status` 数据库记录在请求后被实时更新 |
| TC-06 | 微信通知发送测试 | `notifications` 历史表新增一条 `erp_resolved` 记录，发送状态为 `sent` / `skipped` |
