# 慧元诚 AI-PM V2.0 发版说明

> 发版日期:2026-05-25
> 代码基线:`main @ b732ec2`
> Alembic head:`d2c623c6291a`(`schema_sync_v2_1_cleanup`)

V2.0 在 V1 日报闭环之上,完成了 `docs/implementation-plan.md` 规划的 **全部 13 个 Phase**,并交付 8 项规划外的超预期能力。本说明按 `implementation-plan.md` 原始章节顺序逐项盘点真实完成度。

---

## 一、13 个 Phase 真实完成情况

| § | 功能 | 状态 | 核心交付 |
|---|------|------|----------|
| §1 | 登录认证与安全 | ✅ | JWT 登录、RBAC 中间件、10 预置用户快捷登录、登录审计 `audit_logs`(`routers/auth.py`、`models/audit_log.py`)|
| §2 | 催报机制 | ✅ | APScheduler 三档提醒(17:30 友好 / 18:30 强提醒 / 次日早缺勤);三态过滤(`is_active=True AND status=active`)排除请假/出差/病假;`00:05` 自动到期恢复(`services/scheduled_tasks.py::_get_unreported_users` / `auto_recover_expired_status`)|
| §3 | 通知推送渠道 | ✅ | 统一 `notification_service` 抽象 + 微信/钉钉/邮件/站内信四通道(`services/{wechat_api,dingtalk_api,email_api,notification_service}.py`、`models/notification.py`)|
| §4 | 岗位日报模板差异 | ✅ | 结构化表单(6+7 字段)、☀️晨规划 / 🌙晚复核双模式、报告类型自动分类、质检闭环(未通过不入库)、防重复提交 409 去重(`routers/reports.py` / `routers/simulate.py` / `app/submit-report`)|
| §5 | 附件与多媒体支持 | ✅ | OSS 服务封装、`attachments` 表、附件上传 + 语音转写 8 端点、提交日报集成上传与录音面板(`services/oss_service.py`、`routers/attachments.py`、`routers/asr.py`)|
| §6 | 总经理 AI 对话查询 | ✅ | Tool 注册框架 + Function Calling 多轮编排 + **13 个查询 Tool**(覆盖 reports / projects / sprints / okr / capacity / retro / people / weekly_report),前端 Tool 调用动画 + Markdown 答案(`routers/chat.py`、`services/chat_tools/`)|
| §7 | 历史趋势看板 | ✅ | Sprint 维度聚合 + 评分趋势图(`routers/trends.py`、`services/sprint_aggregator.py`、`app/trends/page.tsx`)|
| §8 | 数据导出 | ✅ | Excel 导出(`routers/export.py`、`app/export/page.tsx`)|
| §9 | KPI 目标设定 | ✅ | 项目健康分引擎 + 仪表盘看板(`services/health_engine.py`、`routers/dashboard.py`)|
| §10 | 部门与项目分组 | ✅ | 项目主数据 + 成员关联 + 项目列表 / 详情 / IPD 看板(`models/project.py`、`models/project_member.py`、`routers/projects.py`、`app/project/[id]`)|
| §11 | OKR 战略对齐 | ✅ | OKRCycle / Objective / KeyResult 三层模型 + AI 自动抽取 KR 进度(`kr_progress_extractor`)+ 季度末自动归档 + 4 Chat Tool + O/KR 树前端(`models/okr.py`、`routers/okr.py`)|
| §12 | 资源负载水位与瓶颈预判 | ✅ | 容量计算引擎(`capacity_engine.py`,22 KB)+ 周一 08:30 自动刷新水位 + 个人水位条 + 部门柱状图 + AI 调配建议 + 5 Chat Tool(`models/capacity.py`、`routers/capacity.py`、`app/capacity/page.tsx`)|
| §13 | AI 驱动自动化复盘 | ✅ | 4 scope(项目 / Sprint / OKR / 季度)复盘生成器 + 4 端点 + 3 Chat Tool + 知识库沉淀 + pgvector 语义检索(`services/retro/`、`routers/retro.py`、`routers/knowledge.py`、`app/retro/page.tsx`)|

**全部 13/13 已完成。**

---

## 二、超预期交付(规划外的 8 项)

| 功能 | 价值 | 关键 commit / 文件 |
|------|------|-------------------|
| IPD 项目阶段门控 | 大中型项目按 IPD 五阶段闸口推进,门控通过才能切阶段 | `feat: complete IPD project stage gating`、`models/project_stage.py`、`models/gate_review.py`、`routers/gates.py` |
| Sprint 燃尽看板 + 关键路径 | 任务级颗粒度、Recharts 燃尽图、关键路径算法、每日 18:00 自动写燃尽快照 | `feat(sprint): Sprint 任务级模型 + 燃尽快照 + 关键路径算法`、`services/critical_path.py`、`models/sprint_task.py` |
| 双模式日报(晨规划 + 晚复核) | 早晨先报计划、晚上回填结果,符合自然工作节奏 | `feat: 双模式日报提交`、`app/submit-report/page.tsx` |
| 质检闭环(未通过不入库) | 评分制 ≥60 入库,驳回需修改后重提,保证 `daily_reports` 数据质量 | `feat: 质检闭环 — 未通过不入库,打回修改后重新提交` |
| 语音转文字(讯飞 / Gemini ASR 双 provider) | 移动端口播提交日报,降低输入门槛 | `services/xunfei_asr.py`、`services/gemini_asr.py`、`routers/asr.py` |
| LLM 多模型选择器 | `llm_registry.yaml` 注册多家供应商,业务侧按场景路由,带 token 配额护栏 | `services/llm_selector.py`、`services/token_guard.py`、`llm_registry.yaml` |
| 微信 / 钉钉 / 邮件三渠道通知 | 催报、风险预警、战情简报全渠道触达;站内信带 `read_at` 已读追踪 + 60s 轮询铃铛 | `feat(notify): 增加多渠道通知服务及微信/钉钉通道支持`、`services/{wechat,dingtalk,email}_api.py`、`components/notification-bell.tsx` |
| ERP 集成接口 | 风险告警带物料号、采购单号,可接金蝶/用友的解卡回写流程 | `routers/erp.py`、`v2_0_erp_enhancement` 迁移 |

---

## 三、Sprint A 收尾(2026-05-22 提交)

最后一批合入的体验优化(对应 commit `70ab380`):

- 侧边栏高级菜单组展开/折叠,`localStorage[sidebar.advancedExpanded]` 持久化
- 用户请假状态闭环(模型 `UserStatus` 枚举 + `_get_unreported_users` 三态过滤 + `auto_recover_expired_status` 到期自动恢复)
- 通知铃铛 60s 轮询未读计数,抽屉打开自动 `markRead`,99+ 红点封顶,10 种模板分色
- 邮件通道补齐(`email_api.py`)

---

## 四、数据库基线

- 当前 Alembic head:`d2c623c6291a`
- 完整迁移链(从 base 到 head):

  ```
  base
    └─ 7c681b8e950c          # initial_schema
    └─ v2_0_baseline         # V2.0 全表 + Week 1-8 schema 一次性建齐
    └─ v2_0_erp_enhancement  # ERP 字段:material_code、po_number
    └─ v2_1_notification_read_at  # 站内信已读时间字段
    └─ 06f98e0a32e8          # users.email
    └─ d2c623c6291a          # schema_sync_v2_1_cleanup(本次)
  ```

- 本次 `schema_sync` 仅做列级元数据对齐(5 个 column comment + `users.dingtalk_userid` 从 unique constraint 转为 unique index),零业务数据风险
- 顺手修复了 `app/models/__init__.py` 漏注册 `AuditLog` 的缺陷,杜绝后续 autogenerate 误判 `audit_logs` 为孤儿表
- `alembic check` 输出 `No new upgrade operations detected`,ORM 与 DB schema **完全对齐**

---

## 五、已知限制

1. **侧边栏"折叠"仅限于高级菜单分组**,尚未实现整体侧边栏收起到 icon-only 模式 — 若产品有此诉求需另开工单。
2. **CORS 与端口耦合于 5173** — 前端 `npm run dev` 强制使用 5173,若被占用需先释放;生产部署不受影响。
3. **`ai_engine_mock.py` 已归档但保留** — 仅供本地无网络环境回归测试,生产路径走 `ai_engine.py`(真实 Gemini)。
4. **APScheduler 任务在单实例下运行** — 当前未做分布式锁,扩容多实例需引入 `apscheduler.jobstores` 共享存储,否则会重复触发。
5. **pgvector 语义检索维度固定为 1536** — 与 OpenAI 兼容,如切换 embedding 维度需新建迁移。
6. **审计日志暂未做归档策略** — `audit_logs` 表单调追加,长期需配套定期归档/分区,否则单表数据量会持续膨胀。
7. **租户隔离按 `tenant_id` 字段实现,无独立 schema/库** — 多租户压测时需关注热点 tenant 的索引选择性。

---

## 六、上线动作清单

1. 备份 `aipm_db` 生产库(尤其是 `audit_logs`、`daily_reports` 两张高价值表)
2. 拉取 `main @ b732ec2`(或更新的 tag)
3. `cd backend && PYTHONPATH=. alembic upgrade head` — 应仅前进到 `d2c623c6291a`
4. `alembic check` 应输出 `No new upgrade operations detected`
5. 按 `DEPLOY.md` 执行预检 + 重启服务
6. 验收:`/health` 200 + 主流程(登录 / 提日报 / 收通知 / AI 对话)端到端 smoke test

---

*本文档随 commit `b732ec2` 一并入库,后续如有补丁请追加 V2.0.x 子条目。*
