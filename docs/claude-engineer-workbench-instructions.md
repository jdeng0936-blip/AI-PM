# Claude 执行指令：工程师任务台与贡献激励升级

## 背景

当前系统已经把经理/执行角色的 `/dashboard` 从管理型监控台收敛为“今日总览”。张毅这类角色现在能看到自己的任务、临期事项、待跟进事项、相关项目和风险。

但当前显示仍偏“统计卡片”，情绪价值不足。用户明确要求：这里需要显示贡献积分，并且要做得更高端，激发工程师的执行欲望和被认可感。

请先理解产品意图，再完善方案，最后执行代码。

## 产品目标

把张毅这类执行/负责人角色的首页，从“任务数量统计”升级为“工程师执行仪表盘”。

用户打开页面后应该立刻感受到：

1. 今天最该推进什么。
2. 完成这些节点能解锁多少贡献积分。
3. 我的交付被系统看见，并且和激励有关。

核心表达不要像后台系统，而要像高质量工程团队的个人作战台。

## 必须保留的原则

- 不删除现有能力。
- 管理员 `admin` 仍保留完整监控台。
- 张毅等 `manager` 角色看轻量任务台，不看未汇报名单、批量软删、数据治理、历史分析大面板。
- 不把“积分”做成廉价排行榜，不鼓励刷量。
- 积分文案要强调真实贡献、节点交付、激励解锁。
- 优先复用现有接口和数据，避免先引入复杂新后端。

## 现有可用数据

当前张毅的任务来源有两类：

1. Sprint 任务：
   - `GET /api/v1/reports/projects/my-active`
   - 前端封装：`getMyActiveProjects`
   - 返回项目及 `tasks`

2. 项目里程碑/贡献节点：
   - `GET /api/v1/projects/{projectId}/milestones`
   - 前端封装：`listProjectMilestones`
   - 关键字段：
     - `title`
     - `status`
     - `target_date`
     - `initial_points`

当前本地库里 `sprint_tasks` 可能为空，但项目里有待完成的 `project_milestones`。因此任务台必须把 pending / in_review 的里程碑节点作为工程师任务来源。

## 建议方案

### 1. 顶部三卡重构

将张毅视图顶部三张卡从：

- 我的任务
- 临期/逾期
- 待跟进

升级为：

- 今日战力
  - 显示任务/节点数量，例如 `7`
  - 辅助文案：`1 个相关项目`

- 待解锁贡献
  - 显示当前未完成节点的 `initial_points` 合计，例如 `200`
  - 辅助文案：`完成节点后进入积分池`

- 临期节点
  - 显示 2 天内到期或已逾期的节点数量
  - 辅助文案：`建议优先推进`

### 2. 增加“建议今天先推进”区域

在任务列表前增加一个推荐区，只展示最多 3 个任务。

排序规则：

1. 已逾期
2. 今天到期
3. 2 天内到期
4. `initial_points` / `story_points` 高
5. 关键路径优先

标题建议：

- `建议今天先推进`
- 副文案：`按截止时间和贡献价值自动排序`

每张推荐卡应展示：

- 任务/节点标题
- 所属项目
- `+30 贡献`
- 截止倒计时：`今天到期` / `还剩 1 天` / `已超 2 天`
- 状态标签
- 行动按钮：`写今日计划` 或 `进入项目`

### 3. 任务列表升级

普通任务列表每项应显示：

- 任务内容
- 所属项目
- 状态
- 优先级，仅 Sprint 任务显示
- `+贡献积分`，里程碑显示 `initial_points`，Sprint 任务可显示 `story_points pt`
- 截止时间和剩余天数

里程碑节点建议显示为：

- `贡献节点`
- `+30 贡献`

不要只显示 `30 积分`，更推荐：

- `+30 贡献`
- `待解锁 30`
- `完成后入账`

### 4. 视觉方向

整体要高端、克制、实用。

建议：

- 不做花哨动画。
- 不做排行榜式刺激。
- 积分使用清晰徽章，例如 `+30 贡献`。
- 临期任务用轻微金色或红色强调。
- 推荐任务可以有更强的视觉优先级，但不要过度装饰。
- 文案要短，工程师一眼能扫懂。

### 5. 数据计算建议

前端先计算即可：

- `pendingContribution = sum(task.story_points or milestone.initial_points)`
- `urgentCount = due <= 2 days or overdue`
- `recommendedTasks = sortedTasks.slice(0, 3)`

后续如需长期维护，再抽后端接口：

`GET /api/v1/me/workbench`

但本次不要先做新接口，除非现有接口无法满足。

## 需要阅读的文件

先阅读并理解：

- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/api/reports.ts`
- `frontend/src/api/milestones.ts`
- `frontend/src/components/sidebar.tsx`
- `frontend/src/app/me/contribution/page.tsx`

必要时再看：

- `backend/app/routers/reports.py`
- `backend/app/routers/milestones.py`
- `backend/app/models/project_milestone.py`
- `backend/app/models/milestone_allocation.py`

## 执行步骤

1. 先总结当前 dashboard 对 `admin` 和 `manager` 的分支逻辑。
2. 完善任务台方案，确认哪些数据来自 Sprint，哪些来自 Milestone。
3. 实现前端改造，优先只改 `frontend/src/app/dashboard/page.tsx`。
4. 如果文案需要同步，可轻微调整贡献积分页，但不要扩大范围。
5. 跑验证：
   - `npm run typecheck`
   - `npm run lint`
6. 用张毅角色检查 `/dashboard`：
   - 不应再显示未汇报名单。
   - 应显示待解锁贡献积分。
   - 应显示任务/节点的贡献值。
   - 应显示推荐推进任务。
7. 用 admin 角色检查 `/dashboard`：
   - 原完整监控台能力不能丢。

## 验收标准

- 张毅进入首页能看到“待解锁贡献”或同等表达。
- 张毅能看到每个任务/节点对应的贡献值。
- 张毅能看到最多 3 个建议优先推进事项。
- 临期/逾期逻辑清楚，不需要用户猜。
- 管理员完整监控台不受影响。
- 前端类型检查和 lint 通过。

## 注意事项

- 当前日期按系统日期判断，2026-05-30。
- 不要把“未汇报名单”重新暴露给张毅。
- 不要把管理者数据治理内容放回经理轻量视图。
- 不要创造假积分；只能用现有 `initial_points` / `story_points`。
- 如果某任务没有截止日期，应显示 `未设截止`，不要参与临期统计。
