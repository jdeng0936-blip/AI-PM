"""
scripts/seed_demo_data.py — 业务 MVP 演示数据种子脚本

目标:为本地 MVP 验证生成"丰满到能跑通所有功能"的演示数据。
覆盖:
  1. 扩展员工(补齐 seed_admin 之外的研发/测试/采购骨干)
  2. 3 个 IPD 项目(分别处于 stage 1 / stage 3 / stage 4)
  3. 项目 5 阶段 + milestones + gate 通过记录
  4. 项目成员(双轨分配)
  5. Q2 2026 OKR 树(1 Cycle + 4 Objective + 10 KR)
  6. Sprint(每个软件/双轨项目 2 个:1 已完成 + 1 进行中)
  7. SprintTask(每 Sprint 8-12 个,含关键路径标记 + 依赖链)
  8. BurndownSnapshot(每 Sprint 全周期每日快照)
  9. CapacitySnapshot(当前 Sprint 每位软件成员的水位)
  10. DailyReport(过去 30 天 × 全员每工作日 1 条,parsed_content 已 AI 解析过的样子)
  11. RiskAlert(8 条管理层卡点,含未解决 + 已升级)
  12. KnowledgeItem(5 条知识库条目,跨 FAQ/最佳实践/经验教训/复盘/模板)

运行:
  cd backend
  python -m scripts.seed_demo_data            # 幂等,可重复运行
  python -m scripts.seed_demo_data --reset    # 清空 demo 数据后重种(谨慎!)
  python -m scripts.seed_demo_data --only=daily_reports,risk_alerts  # 只种特定模块

幂等性:每个模块独立 check 后再 insert,已存在则跳过。
随机性:`random.seed(42)` 固定,保证多次运行数据一致。

⚠️ 注意:本脚本依赖 seed_admin.py 已经跑过(8 个初始用户已存在)。
"""

from __future__ import annotations

import argparse
import asyncio
import os
import random
import secrets
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

# 确保 backend 目录在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from passlib.context import CryptContext  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402

from app.database import AsyncSessionLocal, Base, engine  # noqa: E402
from app.models.capacity import CapacityLevel, CapacitySnapshot  # noqa: E402
from app.models.daily_report import DailyReport  # noqa: E402
from app.models.gate_review import GateDecision, GateReview  # noqa: E402
from app.models.knowledge import KnowledgeCategory, KnowledgeItem  # noqa: E402
from app.models.okr import (  # noqa: E402
    KeyResult,
    Objective,
    OKRCycle,
    OKRCycleType,
    OKRStatus,
)
from app.models.project import (  # noqa: E402
    Project,
    ProjectHealthStatus,
    ProjectStatus,
    ProjectTrack,
)
from app.models.project_member import MemberTrack, ProjectMember  # noqa: E402
from app.models.project_stage import (  # noqa: E402
    STAGE_DEFINITIONS_BY_TRACK,
    ProjectStage,
    StageHealthStatus,
    StageTrack,
)
from app.models.risk_alert import RiskAlert  # noqa: E402
from app.models.sprint import Sprint, SprintStatus  # noqa: E402
from app.models.sprint_task import (  # noqa: E402
    BurndownSnapshot,
    SprintTask,
    TaskPriority,
    TaskStatus,
)
from app.models.user import User, UserRole, UserStatus  # noqa: E402

random.seed(42)
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ═══════════════════════════════════════════════════════════════════
# 全局常量
# ═══════════════════════════════════════════════════════════════════

TODAY = date.today()
# 演示数据的时间锚点:把 demo 锚在"今天",过去 30 天日报 + 未来 30 天计划
DEMO_START = TODAY - timedelta(days=30)
DEMO_END = TODAY + timedelta(days=30)


def is_workday(d: date) -> bool:
    """工作日 = 周一到周五。生产可加节假日表;demo 不必。"""
    return d.weekday() < 5


def workdays_between(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if is_workday(d):
            days.append(d)
        d += timedelta(days=1)
    return days


# ═══════════════════════════════════════════════════════════════════
# 1. 扩展员工(补齐研发/测试骨干)
# ═══════════════════════════════════════════════════════════════════

EXTRA_USERS = [
    # 技术部 — 软件研发
    {
        "name": "张毅",
        "wechat_userid": "zhang_yi",
        "department": "技术部",
        "job_title": "高级研发工程师",
        "role": UserRole.employee,
        "phone": "13800000001",
        "email": "zhang.yi@huiyuancheng.com",
        "story_points_capacity": 10,
    },
    {
        "name": "郭震",
        "wechat_userid": "guo_zhen",
        "department": "技术部",
        "job_title": "研发工程师",
        "role": UserRole.employee,
        "phone": "13800000002",
        "email": "guo.zhen@huiyuancheng.com",
        "story_points_capacity": 8,
    },
    {
        "name": "新雷",
        "wechat_userid": "xin_lei",
        "department": "技术部",
        "job_title": "AI 集成工程师",
        "role": UserRole.employee,
        "phone": "13800000003",
        "email": "xin.lei@huiyuancheng.com",
        "story_points_capacity": 10,
    },
    # 技术部 — 硬件研发
    {
        "name": "林跃文",
        "wechat_userid": "lin_yuewen",
        "department": "技术部",
        "job_title": "硬件工程师",
        "role": UserRole.employee,
        "phone": "13800000004",
        "email": "lin.yuewen@huiyuancheng.com",
        "story_points_capacity": 8,
    },
    {
        "name": "郑韬慧",
        "wechat_userid": "zheng_taohui",
        "department": "技术部",
        "job_title": "测试工程师",
        "role": UserRole.employee,
        "phone": "13800000005",
        "email": "zheng.taohui@huiyuancheng.com",
        "story_points_capacity": 8,
    },
    # 商务 / 销售辅助
    {
        "name": "陈思琪",
        "wechat_userid": "chen_siqi",
        "department": "商务部",
        "job_title": "商务专员",
        "role": UserRole.employee,
        "phone": "13800000006",
        "email": "chen.siqi@huiyuancheng.com",
        "story_points_capacity": 6,
    },
]


async def seed_extra_users(db, admin_id):
    print("\n[1/12] 扩展员工…")
    added = 0
    for u in EXTRA_USERS:
        existing = await db.execute(select(User).where(User.wechat_userid == u["wechat_userid"]))
        if existing.scalar_one_or_none():
            continue
        temporary_password = secrets.token_urlsafe(12)
        user = User(
            name=u["name"],
            wechat_userid=u["wechat_userid"],
            phone=u["phone"],
            email=u["email"],
            department=u["department"],
            job_title=u["job_title"],
            role=u["role"],
            hashed_password=pwd_context.hash(temporary_password),
            must_change_password=True,
            is_active=True,
            status=UserStatus.active,
            story_points_capacity=u["story_points_capacity"],
        )
        db.add(user)
        added += 1
    await db.commit()
    print(f"  ✅ 新增 {added} 个员工(已存在则跳过,新用户已生成随机临时密码)")


# ═══════════════════════════════════════════════════════════════════
# 2-4. 项目 + 阶段 + 成员
# ═══════════════════════════════════════════════════════════════════

PROJECTS = [
    {
        "code": "P2026-001",
        "name": "206 智能样机研发与量产",
        "description": "面向工业场景的下一代智能终端,软硬双轨并行,Q2 完成 TR6,Q3 量产。",
        "track": ProjectTrack.dual,
        "current_stage": 3,  # 双轨并行开发期
        "health_status": ProjectHealthStatus.yellow,
        "health_score": 78,
        "planned_launch_date": TODAY + timedelta(days=120),
        "budget_total": Decimal("2800000"),
        "budget_spent": Decimal("1450000"),
        "member_specs": [
            ("林跃文", MemberTrack.hardware, "硬件负责人"),
            ("郑韬慧", MemberTrack.hardware, "测试工程师"),
            ("张毅", MemberTrack.software, "软件负责人 / Sprint Lead"),
            ("郭震", MemberTrack.software, "后端研发"),
            ("新雷", MemberTrack.software, "AI 集成"),
            ("技术部长", MemberTrack.both, "项目总负责人"),
            ("采购经理", MemberTrack.hardware, "物料采购"),
        ],
        "stage_health": {
            1: (StageHealthStatus.green, 100, 95),
            2: (StageHealthStatus.green, 100, 92),
            3: (StageHealthStatus.yellow, 62, 75),  # 当前阶段
            4: (StageHealthStatus.locked, 0, 100),
            5: (StageHealthStatus.locked, 0, 100),
        },
        "passed_gates": [1, 2],
    },
    {
        "code": "P2026-002",
        "name": "智能仓储调度系统",
        "description": "为仓储部开发的 AI 调度系统,纯软件项目,目标 Q2 上线试运行。",
        "track": ProjectTrack.software,
        "current_stage": 4,  # 测试验收期
        "health_status": ProjectHealthStatus.green,
        "health_score": 88,
        "planned_launch_date": TODAY + timedelta(days=45),
        "budget_total": Decimal("680000"),
        "budget_spent": Decimal("510000"),
        "member_specs": [
            ("张毅", MemberTrack.software, "技术负责人"),
            ("郭震", MemberTrack.software, "后端"),
            ("新雷", MemberTrack.software, "AI 调度算法"),
            ("仓管", MemberTrack.both, "业务方"),
            ("技术部长", MemberTrack.both, "PM"),
        ],
        "stage_health": {
            1: (StageHealthStatus.green, 100, 96),
            2: (StageHealthStatus.green, 100, 94),
            3: (StageHealthStatus.green, 100, 90),
            4: (StageHealthStatus.green, 55, 88),
            5: (StageHealthStatus.locked, 0, 100),
        },
        "passed_gates": [1, 2, 3],
    },
    {
        "code": "P2026-003",
        "name": "客户智能合同审核",
        "description": "用大模型自动审核销售合同条款,新立项,本季度完成立项 + 设计。",
        "track": ProjectTrack.software,
        "current_stage": 1,  # 立项期
        "health_status": ProjectHealthStatus.green,
        "health_score": 95,
        "planned_launch_date": TODAY + timedelta(days=180),
        "budget_total": Decimal("420000"),
        "budget_spent": Decimal("38000"),
        "member_specs": [
            ("销售部长", MemberTrack.both, "业务方"),
            ("新雷", MemberTrack.software, "AI 方案设计"),
            ("商务经理", MemberTrack.both, "需求收集"),
        ],
        "stage_health": {
            1: (StageHealthStatus.green, 70, 95),
            2: (StageHealthStatus.locked, 0, 100),
            3: (StageHealthStatus.locked, 0, 100),
            4: (StageHealthStatus.locked, 0, 100),
            5: (StageHealthStatus.locked, 0, 100),
        },
        "passed_gates": [],
    },
]


async def get_user_id_by_name(db, name: str) -> Optional[str]:
    """容忍重名:取最早创建的同名用户(LIMIT 1)。"""
    r = await db.execute(select(User.id).where(User.name == name).order_by(User.created_at).limit(1))
    return r.scalars().first()


async def seed_projects_and_stages(db, admin_id):
    print("\n[2-4/12] 项目 + 阶段 + 成员…")
    p_count, s_count, m_count = 0, 0, 0

    for p_spec in PROJECTS:
        # 检查项目是否已存在
        existing = await db.execute(select(Project).where(Project.code == p_spec["code"]))
        proj = existing.scalar_one_or_none()
        if proj is None:
            proj = Project(
                code=p_spec["code"],
                name=p_spec["name"],
                description=p_spec["description"],
                track=p_spec["track"],
                current_stage=p_spec["current_stage"],
                status=ProjectStatus.active,
                health_status=p_spec["health_status"],
                health_score=p_spec["health_score"],
                planned_launch_date=p_spec["planned_launch_date"],
                budget_total=p_spec["budget_total"],
                budget_spent=p_spec["budget_spent"],
                budget_alert_threshold=0.8,
                created_by=admin_id,
            )
            db.add(proj)
            await db.flush()  # 拿到 proj.id
            p_count += 1

        # ── 阶段 ─────────────────────────────────────────────────
        existing_stages = await db.execute(select(ProjectStage).where(ProjectStage.project_id == proj.id))
        if existing_stages.first() is None:
            stage_defs = STAGE_DEFINITIONS_BY_TRACK[proj.track.value]
            # 按 typical_duration_days 串接日期
            cursor = TODAY - timedelta(days=90)  # 项目 90 天前开始
            for num, name, track_str, duration in stage_defs:
                planned_start = cursor
                planned_end = cursor + timedelta(days=duration)
                hs, prog, score = p_spec["stage_health"].get(num, (StageHealthStatus.green, 0, 100))

                # 已完成阶段填 actual_start/end;当前阶段填 actual_start;未开始无
                actual_start = planned_start if num <= proj.current_stage else None
                actual_end = planned_end if num < proj.current_stage else None

                # 里程碑(硬件阶段才有)
                milestones = []
                if num == 2 and proj.track == ProjectTrack.dual:
                    milestones = [
                        {
                            "name": "硬件方案评审",
                            "planned_date": str(planned_start + timedelta(days=7)),
                            "actual_date": str(planned_start + timedelta(days=8)),
                            "status": "done",
                        },
                        {
                            "name": "软件架构评审",
                            "planned_date": str(planned_start + timedelta(days=14)),
                            "actual_date": str(planned_start + timedelta(days=14)),
                            "status": "done",
                        },
                        {
                            "name": "联调接口握手",
                            "planned_date": str(planned_end - timedelta(days=2)),
                            "actual_date": str(planned_end - timedelta(days=1)),
                            "status": "done",
                        },
                    ]
                elif num == 3 and proj.track == ProjectTrack.dual:
                    milestones = [
                        {
                            "name": "PCB 样机贴片",
                            "planned_date": str(planned_start + timedelta(days=20)),
                            "actual_date": str(planned_start + timedelta(days=23)),
                            "status": "done",
                        },
                        {
                            "name": "固件 v0.5 烧录",
                            "planned_date": str(planned_start + timedelta(days=35)),
                            "actual_date": None,
                            "status": "in_progress",
                        },
                        {
                            "name": "整机联调",
                            "planned_date": str(planned_start + timedelta(days=55)),
                            "actual_date": None,
                            "status": "pending",
                        },
                    ]
                elif num == 4 and proj.code == "P2026-002":
                    milestones = [
                        {
                            "name": "UAT 用户验收",
                            "planned_date": str(planned_start + timedelta(days=10)),
                            "actual_date": None,
                            "status": "in_progress",
                        },
                        {
                            "name": "压力测试",
                            "planned_date": str(planned_start + timedelta(days=15)),
                            "actual_date": None,
                            "status": "pending",
                        },
                    ]

                stage = ProjectStage(
                    project_id=proj.id,
                    stage_number=num,
                    stage_name=name,
                    track=StageTrack(track_str),
                    planned_start=planned_start,
                    planned_end=planned_end,
                    actual_start=actual_start,
                    actual_end=actual_end,
                    health_status=hs,
                    progress_pct=prog,
                    health_score=score,
                    milestones=milestones,
                    gate_passed=(num in p_spec["passed_gates"]),
                    gate_passed_at=(datetime.utcnow() - timedelta(days=30) if num in p_spec["passed_gates"] else None),
                    created_by=admin_id,
                )
                db.add(stage)
                s_count += 1
                cursor = planned_end + timedelta(days=1)

        # ── 成员 ─────────────────────────────────────────────────
        existing_members = await db.execute(select(ProjectMember).where(ProjectMember.project_id == proj.id))
        if existing_members.first() is None:
            for member_name, track, role in p_spec["member_specs"]:
                uid = await get_user_id_by_name(db, member_name)
                if uid is None:
                    print(f"    ⚠️  用户 '{member_name}' 不存在,跳过")
                    continue
                pm = ProjectMember(
                    project_id=proj.id,
                    user_id=uid,
                    track=track,
                    role_in_project=role,
                    joined_at=TODAY - timedelta(days=85),
                    created_by=admin_id,
                )
                db.add(pm)
                m_count += 1

    await db.commit()
    print(f"  ✅ 项目 +{p_count}  阶段 +{s_count}  成员 +{m_count}")


# ═══════════════════════════════════════════════════════════════════
# 5. Gate Reviews(已通过的关卡评审)
# ═══════════════════════════════════════════════════════════════════

GATE_NAMES = {
    1: "立项评审 (Gate 1)",
    2: "设计评审 (Gate 2)",
    3: "发布就绪评审 (Gate 3/TR6)",
    4: "量产放行 (Gate 4)",
}

GATE_AI_SUMMARIES = {
    1: "立项阶段 14 天内完成可行性论证、预算 280 万元已确认、商业指标(单台目标毛利 28%)已对齐。技术风险已识别:核心传感器 IC 货期 8 周,采购已下单。",
    2: "设计阶段 21 天完成,硬件原理图 / PCB v2 已评审通过,软件接口契约(REST+MQTT)已与硬件团队握手。Sprint 1 已规划 32 故事点。",
    3: "TR6 评审:性能 19/19 指标 100% 达成,UAT 通过率 96%,压测 3 倍峰值无降级。具备发布条件,放行量产准备。",
}


async def seed_gate_reviews(db, admin_id):
    print("\n[5/12] Gate Reviews…")
    added = 0
    for p_spec in PROJECTS:
        r = await db.execute(select(Project).where(Project.code == p_spec["code"]))
        proj = r.scalar_one_or_none()
        if not proj:
            continue
        for gate_num in p_spec["passed_gates"]:
            existing = await db.execute(
                select(GateReview).where(
                    GateReview.project_id == proj.id,
                    GateReview.gate_number == gate_num,
                )
            )
            if existing.scalar_one_or_none():
                continue
            review = GateReview(
                project_id=proj.id,
                gate_number=gate_num,
                gate_name=GATE_NAMES[gate_num],
                reviewer_id=admin_id,
                decision=GateDecision.pass_,
                decision_notes=f"按 IPD 标准通过 Gate {gate_num},允许资源放行下一阶段。",
                ai_summary=GATE_AI_SUMMARIES.get(gate_num, ""),
                reviewed_at=datetime.utcnow() - timedelta(days=(4 - gate_num) * 15),
                created_by=admin_id,
            )
            db.add(review)
            added += 1
    await db.commit()
    print(f"  ✅ Gate Review +{added}")


# ═══════════════════════════════════════════════════════════════════
# 6. OKR 树(1 Cycle + 4 Objective + 10 KR)
# ═══════════════════════════════════════════════════════════════════


async def seed_okr(db, admin_id):
    print("\n[6/12] OKR Q2 2026 树…")

    # OKR Cycle
    cycle_name = "2026Q2"
    existing = await db.execute(select(OKRCycle).where(OKRCycle.name == cycle_name))
    cycle = existing.scalar_one_or_none()
    if cycle is None:
        cycle = OKRCycle(
            name=cycle_name,
            cycle_type=OKRCycleType.quarterly,
            start_date=date(TODAY.year, 4, 1) if TODAY.month >= 4 else date(TODAY.year - 1, 4, 1),
            end_date=date(TODAY.year, 6, 30) if TODAY.month >= 4 else date(TODAY.year - 1, 6, 30),
            status=OKRStatus.active,
            created_by=admin_id,
        )
        db.add(cycle)
        await db.flush()
        print(f"  ✅ OKR Cycle '{cycle_name}' 已创建")
    else:
        print(f"  ⏭️  OKR Cycle '{cycle_name}' 已存在")

    # 项目 ID 查找
    r1 = await db.execute(select(Project).where(Project.code == "P2026-001"))
    p206 = r1.scalar_one_or_none()
    r2 = await db.execute(select(Project).where(Project.code == "P2026-002"))
    p_storage = r2.scalar_one_or_none()

    # 4 Objectives — owner / KR list
    admin_uid = admin_id
    tech_director_uid = await get_user_id_by_name(db, "技术部长")
    sales_director_uid = await get_user_id_by_name(db, "销售部长")
    zhang_yi_uid = await get_user_id_by_name(db, "张毅")
    xin_lei_uid = await get_user_id_by_name(db, "新雷")
    lin_uid = await get_user_id_by_name(db, "林跃文")

    objectives_spec = [
        {
            "title": "Q2 完成 206 智能样机 TR6,具备量产条件",
            "description": "公司 Q2 战略级目标,卡点直接升级到总经理。",
            "owner_id": admin_uid,
            "project_id": p206.id if p206 else None,
            "weight": 1.0,
            "progress": 62.0,
            "krs": [
                {
                    "title": "PCB v2 量产工艺评审通过",
                    "target_value": 1,
                    "current_value": 1,
                    "unit": "次",
                    "metric_type": "count",
                    "owner_id": lin_uid,
                    "confidence": 0.9,
                },
                {
                    "title": "固件 v1.0 通过 UAT,缺陷收敛到 <= 5 条 P1+",
                    "target_value": 5,
                    "current_value": 8,
                    "unit": "条",
                    "metric_type": "count",
                    "owner_id": zhang_yi_uid,
                    "confidence": 0.6,
                },
                {
                    "title": "AI 集成模块响应延迟 P95 ≤ 800ms",
                    "target_value": 800,
                    "current_value": 920,
                    "unit": "ms",
                    "metric_type": "count",
                    "owner_id": xin_lei_uid,
                    "confidence": 0.55,
                },
            ],
        },
        {
            "title": "智能仓储系统上线试运行,验证 AI 调度收益",
            "description": "技术部 Q2 目标,验收口径:WMS 调度效率提升 ≥ 20%。",
            "owner_id": tech_director_uid,
            "project_id": p_storage.id if p_storage else None,
            "weight": 0.7,
            "progress": 78.0,
            "krs": [
                {
                    "title": "完成 UAT 测试覆盖率 ≥ 95%",
                    "target_value": 95,
                    "current_value": 88,
                    "unit": "%",
                    "metric_type": "percentage",
                    "owner_id": zhang_yi_uid,
                    "confidence": 0.75,
                },
                {
                    "title": "压测峰值 QPS ≥ 1500",
                    "target_value": 1500,
                    "current_value": 1820,
                    "unit": "QPS",
                    "metric_type": "count",
                    "owner_id": zhang_yi_uid,
                    "confidence": 0.95,
                },
                {
                    "title": "切换至生产环境且 7 天 P0 故障 = 0",
                    "target_value": 1,
                    "current_value": 0,
                    "unit": "次",
                    "metric_type": "count",
                    "owner_id": tech_director_uid,
                    "confidence": 0.5,
                },
            ],
        },
        {
            "title": "Q2 销售合同审核效率提升 50%",
            "description": "商务/销售 Q2 战略目标,通过 P2026-003 AI 项目落地。",
            "owner_id": sales_director_uid,
            "project_id": None,
            "weight": 0.6,
            "progress": 15.0,
            "krs": [
                {
                    "title": "完成 P2026-003 立项与设计评审",
                    "target_value": 2,
                    "current_value": 1,
                    "unit": "个 Gate",
                    "metric_type": "count",
                    "owner_id": sales_director_uid,
                    "confidence": 0.8,
                },
                {
                    "title": "Q2 末试点 10 份真实合同 AI 审核",
                    "target_value": 10,
                    "current_value": 0,
                    "unit": "份",
                    "metric_type": "count",
                    "owner_id": sales_director_uid,
                    "confidence": 0.4,
                },
            ],
        },
        {
            "title": "团队工程效能与质量基线建设",
            "description": "技术部内部目标,服务于长期可持续交付能力。",
            "owner_id": tech_director_uid,
            "project_id": None,
            "weight": 0.4,
            "progress": 70.0,
            "krs": [
                {
                    "title": "单测覆盖率 ≥ 70%",
                    "target_value": 70,
                    "current_value": 62,
                    "unit": "%",
                    "metric_type": "percentage",
                    "owner_id": zhang_yi_uid,
                    "confidence": 0.7,
                },
                {
                    "title": "CI 主干通过率 ≥ 95%",
                    "target_value": 95,
                    "current_value": 98,
                    "unit": "%",
                    "metric_type": "percentage",
                    "owner_id": tech_director_uid,
                    "confidence": 0.95,
                },
            ],
        },
    ]

    added_o, added_kr = 0, 0
    for o_spec in objectives_spec:
        existing_o = await db.execute(
            select(Objective).where(
                Objective.cycle_id == cycle.id,
                Objective.title == o_spec["title"],
            )
        )
        obj = existing_o.scalar_one_or_none()
        if obj is None:
            obj = Objective(
                cycle_id=cycle.id,
                project_id=o_spec["project_id"],
                owner_id=o_spec["owner_id"],
                title=o_spec["title"],
                description=o_spec["description"],
                weight=o_spec["weight"],
                progress=o_spec["progress"],
                status=OKRStatus.active,
                created_by=admin_id,
            )
            db.add(obj)
            await db.flush()
            added_o += 1
        for kr_spec in o_spec["krs"]:
            existing_kr = await db.execute(
                select(KeyResult).where(
                    KeyResult.objective_id == obj.id,
                    KeyResult.title == kr_spec["title"],
                )
            )
            if existing_kr.scalar_one_or_none():
                continue
            kr = KeyResult(
                objective_id=obj.id,
                owner_id=kr_spec["owner_id"],
                title=kr_spec["title"],
                metric_type=kr_spec["metric_type"],
                target_value=kr_spec["target_value"],
                current_value=kr_spec["current_value"],
                confidence=kr_spec["confidence"],
                unit=kr_spec["unit"],
                description=kr_spec.get("description"),
                created_by=admin_id,
            )
            db.add(kr)
            added_kr += 1

    await db.commit()
    print(f"  ✅ Objective +{added_o}  KR +{added_kr}")


# ═══════════════════════════════════════════════════════════════════
# 7-9. Sprint + Task + Burndown
# ═══════════════════════════════════════════════════════════════════

# 任务模板(为软件项目准备的真实任务名)
TASK_TEMPLATES_206 = [
    ("MQTT 设备接入协议联调", "p0", 5, True, ["xin_lei"]),
    ("固件 OTA 升级模块开发", "p1", 8, False, ["xin_lei"]),
    ("后端设备状态聚合接口", "p0", 5, True, ["zhang_yi"]),
    ("Web 控制台:设备列表 + 状态卡片", "p1", 5, False, ["guo_zhen"]),
    ("Web 控制台:告警实时推送(WebSocket)", "p2", 3, False, ["guo_zhen"]),
    ("AI 故障预测模型 v0.3 接入", "p1", 8, False, ["xin_lei"]),
    ("接口压测脚本 + 报告", "p2", 3, False, ["zhang_yi"]),
    ("文档:OpenAPI 3.0 输出", "p3", 2, False, ["guo_zhen"]),
]

TASK_TEMPLATES_STORAGE = [
    ("UAT 用例库梳理(120+ 用例)", "p0", 5, True, ["zhang_yi"]),
    ("调度算法 v2 灰度切流", "p0", 8, True, ["xin_lei"]),
    ("性能压测:1500 QPS 长跑", "p1", 5, False, ["zhang_yi"]),
    ("数据迁移工具", "p1", 3, False, ["guo_zhen"]),
    ("仓管前端反馈页面", "p2", 3, False, ["guo_zhen"]),
    ("Bug 修复:并发分配重复问题", "p0", 5, True, ["zhang_yi"]),
    ("监控看板 Grafana 接入", "p3", 2, False, ["xin_lei"]),
]


async def seed_sprints_tasks_burndown(db, admin_id):
    print("\n[7-9/12] Sprint + SprintTask + Burndown…")

    # 拿到项目 + 用户映射
    def make_task_payloads(templates, sprint_member_uids: dict[str, str]):
        items = []
        for title, prio, pts, on_cp, assignee_keys in templates:
            aid = sprint_member_uids.get(assignee_keys[0]) if assignee_keys else None
            items.append(
                {
                    "title": title,
                    "priority": TaskPriority(prio),
                    "story_points": pts,
                    "is_on_critical_path": on_cp,
                    "assignee_id": aid,
                }
            )
        return items

    # 用户 wechat_userid → uid 映射(限定软件研发)
    wechat_to_uid = {}
    for wid in ("zhang_yi", "guo_zhen", "xin_lei"):
        r = await db.execute(select(User).where(User.wechat_userid == wid))
        u = r.scalar_one_or_none()
        if u:
            wechat_to_uid[wid] = u.id

    s_count, t_count, b_count = 0, 0, 0

    # P2026-001 — 2 个 Sprint
    p206 = (await db.execute(select(Project).where(Project.code == "P2026-001"))).scalar_one_or_none()
    if p206:
        stage3 = (
            await db.execute(
                select(ProjectStage).where(
                    ProjectStage.project_id == p206.id,
                    ProjectStage.stage_number == 3,
                )
            )
        ).scalar_one_or_none()

        sprint_specs = [
            {
                "sprint_number": 1,
                "goal": "完成 PCB v2 联调 + 固件骨架,打通设备到云的端到端链路。",
                "start_date": TODAY - timedelta(days=28),
                "end_date": TODAY - timedelta(days=15),
                "status": SprintStatus.completed,
                "planned_pts": 32,
                "completed_pts": 28,
                "task_template": TASK_TEMPLATES_206[:6],
                "task_done_ratio": 0.83,  # 大部分完成
            },
            {
                "sprint_number": 2,
                "goal": "完成设备状态聚合 + 告警推送,推 Sprint 1 P1 余项收口。",
                "start_date": TODAY - timedelta(days=14),
                "end_date": TODAY,
                "status": SprintStatus.active,
                "planned_pts": 36,
                "completed_pts": 18,  # 进行中
                "task_template": TASK_TEMPLATES_206,
                "task_done_ratio": 0.45,  # 进行中
            },
        ]
        for spec in sprint_specs:
            existing = await db.execute(
                select(Sprint).where(
                    Sprint.project_id == p206.id,
                    Sprint.sprint_number == spec["sprint_number"],
                )
            )
            sp = existing.scalar_one_or_none()
            if sp is None:
                sp = Sprint(
                    project_id=p206.id,
                    stage_id=stage3.id if stage3 else None,
                    sprint_number=spec["sprint_number"],
                    goal=spec["goal"],
                    start_date=spec["start_date"],
                    end_date=spec["end_date"],
                    health_score=82 if spec["status"] == SprintStatus.active else 88,
                    planned_story_points=spec["planned_pts"],
                    completed_story_points=spec["completed_pts"],
                    status=spec["status"],
                    retrospective=(
                        {
                            "went_well": ["接口契约写得清楚,联调顺畅", "AI 模块封装到位"],
                            "improve": ["PCB 第一版有飞线,占用 2 天返工"],
                            "action_items": [
                                {
                                    "item": "PCB 评审引入 DFM checklist",
                                    "owner": "林跃文",
                                    "due": str(TODAY + timedelta(days=30)),
                                },
                            ],
                        }
                        if spec["status"] == SprintStatus.completed
                        else None
                    ),
                    created_by=admin_id,
                )
                db.add(sp)
                await db.flush()
                s_count += 1

            # Tasks
            existing_t = await db.execute(select(SprintTask).where(SprintTask.sprint_id == sp.id))
            if existing_t.first() is None:
                payloads = make_task_payloads(spec["task_template"], wechat_to_uid)
                done_n = int(len(payloads) * spec["task_done_ratio"])
                prev_task_id = None
                for i, p in enumerate(payloads):
                    if i < done_n:
                        st = TaskStatus.done
                        actual_start = spec["start_date"] + timedelta(days=1)
                        actual_end = spec["start_date"] + timedelta(days=random.randint(3, 10))
                        actual_pts = p["story_points"]
                    elif i == done_n:
                        st = TaskStatus.blocked
                        actual_start = spec["start_date"] + timedelta(days=3)
                        actual_end = None
                        actual_pts = None
                    elif i < done_n + 3:
                        st = TaskStatus.in_progress
                        actual_start = spec["start_date"] + timedelta(days=2)
                        actual_end = None
                        actual_pts = None
                    else:
                        st = TaskStatus.todo
                        actual_start = None
                        actual_end = None
                        actual_pts = None

                    t = SprintTask(
                        sprint_id=sp.id,
                        assignee_id=p["assignee_id"],
                        title=p["title"],
                        description=f"Sprint #{spec['sprint_number']} 任务 — {p['title']}",
                        story_points=p["story_points"],
                        status=st,
                        priority=p["priority"],
                        is_on_critical_path=p["is_on_critical_path"],
                        depends_on=[str(prev_task_id)] if prev_task_id and i % 3 == 0 else None,
                        planned_start=spec["start_date"],
                        planned_end=spec["end_date"],
                        actual_start=actual_start,
                        actual_end=actual_end,
                        actual_story_points=actual_pts,
                        created_by=admin_id,
                    )
                    db.add(t)
                    await db.flush()
                    prev_task_id = t.id
                    t_count += 1

            # Burndown 快照(全程每日一条)
            existing_b = await db.execute(select(BurndownSnapshot).where(BurndownSnapshot.sprint_id == sp.id))
            if existing_b.first() is None:
                total = spec["planned_pts"]
                duration = (spec["end_date"] - spec["start_date"]).days + 1
                # 已完成 Sprint 走完整曲线;进行中只到 today
                cur_date = spec["start_date"]
                completed_so_far = 0
                day_idx = 0
                while cur_date <= min(spec["end_date"], TODAY):
                    # 模拟实际曲线:前 1/3 平,中段加速,末端减速
                    expected_done = spec["completed_pts"] * (day_idx + 1) / duration
                    # 加点波动
                    expected_done += random.randint(-1, 1)
                    completed_so_far = max(0, min(spec["completed_pts"], int(expected_done)))
                    bs = BurndownSnapshot(
                        sprint_id=sp.id,
                        snapshot_date=cur_date,
                        completed_points=completed_so_far,
                        remaining_points=max(0, total - completed_so_far),
                        total_points=total,
                        done_count=int(completed_so_far / 4),
                        in_progress_count=2,
                        blocked_count=1 if day_idx > 3 and day_idx < duration - 3 else 0,
                        todo_count=max(0, len(spec["task_template"]) - int(completed_so_far / 4) - 3),
                        created_by=admin_id,
                    )
                    db.add(bs)
                    b_count += 1
                    cur_date += timedelta(days=1)
                    day_idx += 1

    # P2026-002 — 1 个进行中 Sprint
    p_storage = (await db.execute(select(Project).where(Project.code == "P2026-002"))).scalar_one_or_none()
    if p_storage:
        stage4 = (
            await db.execute(
                select(ProjectStage).where(
                    ProjectStage.project_id == p_storage.id,
                    ProjectStage.stage_number == 4,
                )
            )
        ).scalar_one_or_none()

        existing = await db.execute(
            select(Sprint).where(
                Sprint.project_id == p_storage.id,
                Sprint.sprint_number == 1,
            )
        )
        sp = existing.scalar_one_or_none()
        if sp is None:
            sp = Sprint(
                project_id=p_storage.id,
                stage_id=stage4.id if stage4 else None,
                sprint_number=1,
                goal="完成 UAT 测试 + 调度算法 v2 上线,达成上线条件。",
                start_date=TODAY - timedelta(days=10),
                end_date=TODAY + timedelta(days=4),
                health_score=85,
                planned_story_points=31,
                completed_story_points=16,
                status=SprintStatus.active,
                created_by=admin_id,
            )
            db.add(sp)
            await db.flush()
            s_count += 1

        existing_t = await db.execute(select(SprintTask).where(SprintTask.sprint_id == sp.id))
        if existing_t.first() is None:
            payloads = make_task_payloads(TASK_TEMPLATES_STORAGE, wechat_to_uid)
            for i, p in enumerate(payloads):
                if i < 3:
                    st = TaskStatus.done
                    actual_start = sp.start_date
                    actual_end = sp.start_date + timedelta(days=random.randint(2, 6))
                    actual_pts = p["story_points"]
                elif i == 3:
                    st = TaskStatus.blocked
                    actual_start = sp.start_date + timedelta(days=2)
                    actual_end = None
                    actual_pts = None
                else:
                    st = TaskStatus.in_progress if i < 5 else TaskStatus.todo
                    actual_start = sp.start_date + timedelta(days=3) if st == TaskStatus.in_progress else None
                    actual_end = None
                    actual_pts = None

                t = SprintTask(
                    sprint_id=sp.id,
                    assignee_id=p["assignee_id"],
                    title=p["title"],
                    description=f"P2026-002 Sprint 1 — {p['title']}",
                    story_points=p["story_points"],
                    status=st,
                    priority=p["priority"],
                    is_on_critical_path=p["is_on_critical_path"],
                    planned_start=sp.start_date,
                    planned_end=sp.end_date,
                    actual_start=actual_start,
                    actual_end=actual_end,
                    actual_story_points=actual_pts,
                    created_by=admin_id,
                )
                db.add(t)
                t_count += 1

        # Burndown
        existing_b = await db.execute(select(BurndownSnapshot).where(BurndownSnapshot.sprint_id == sp.id))
        if existing_b.first() is None:
            cur_date = sp.start_date
            day_idx = 0
            duration = (sp.end_date - sp.start_date).days + 1
            while cur_date <= TODAY:
                completed = min(16, int(16 * (day_idx + 1) / 10) + random.randint(-1, 1))
                completed = max(0, completed)
                bs = BurndownSnapshot(
                    sprint_id=sp.id,
                    snapshot_date=cur_date,
                    completed_points=completed,
                    remaining_points=max(0, 31 - completed),
                    total_points=31,
                    done_count=int(completed / 5),
                    in_progress_count=2,
                    blocked_count=1 if day_idx >= 3 else 0,
                    todo_count=max(0, 7 - int(completed / 5) - 3),
                    created_by=admin_id,
                )
                db.add(bs)
                b_count += 1
                cur_date += timedelta(days=1)
                day_idx += 1

    await db.commit()
    print(f"  ✅ Sprint +{s_count}  Task +{t_count}  Burndown +{b_count}")


# ═══════════════════════════════════════════════════════════════════
# 10. CapacitySnapshot(当前 Sprint 每位软件成员的水位)
# ═══════════════════════════════════════════════════════════════════


async def seed_capacity_snapshots(db, admin_id):
    print("\n[10/12] CapacitySnapshot…")
    # 找所有 active sprints
    r = await db.execute(select(Sprint).where(Sprint.status == SprintStatus.active))
    active_sprints = list(r.scalars())

    added = 0
    for sp in active_sprints:
        # 取该 sprint 的所有 task assignees
        r2 = await db.execute(
            select(
                SprintTask.assignee_id, SprintTask.story_points, SprintTask.status, SprintTask.is_on_critical_path
            ).where(SprintTask.sprint_id == sp.id)
        )
        tasks = list(r2.all())
        # 按 assignee 聚合
        agg: dict = {}
        for aid, pts, status, on_cp in tasks:
            if aid is None:
                continue
            d = agg.setdefault(aid, {"allocated": 0, "completed": 0, "active": 0, "blocked": 0, "cp": 0})
            if status in (TaskStatus.todo, TaskStatus.in_progress, TaskStatus.blocked):
                d["allocated"] += pts
                d["active"] += 1
            if status == TaskStatus.done:
                d["completed"] += pts
            if status == TaskStatus.blocked:
                d["blocked"] += 1
            if on_cp:
                d["cp"] += 1

        for assignee_id, stat in agg.items():
            existing = await db.execute(
                select(CapacitySnapshot).where(
                    CapacitySnapshot.sprint_id == sp.id,
                    CapacitySnapshot.user_id == assignee_id,
                )
            )
            if existing.scalar_one_or_none():
                continue
            # 拿 user 的 base capacity
            user_r = await db.execute(select(User).where(User.id == assignee_id))
            user = user_r.scalar_one_or_none()
            base = user.story_points_capacity if user else 8

            util = stat["allocated"] / base if base > 0 else 0
            if util < 0.3:
                level = CapacityLevel.idle
            elif util < 0.8:
                level = CapacityLevel.healthy
            elif util < 1.0:
                level = CapacityLevel.high
            else:
                level = CapacityLevel.overload

            suggestion = None
            if level == CapacityLevel.overload:
                suggestion = (
                    f"建议把 1 个 P2 任务从该成员转出,或者把 Sprint 1 P3 任务延后。"
                    f"当前占用率 {util:.0%},超出健康水位。"
                )
            elif level == CapacityLevel.idle:
                suggestion = f"该成员当前占用率仅 {util:.0%},可承接更多 P1 任务。"

            cs = CapacitySnapshot(
                user_id=assignee_id,
                sprint_id=sp.id,
                base_capacity=base,
                effective_capacity=base,
                allocated_points=stat["allocated"],
                completed_points=stat["completed"],
                active_task_count=stat["active"],
                blocked_task_count=stat["blocked"],
                critical_path_task_count=stat["cp"],
                utilization=util,
                level=level,
                velocity_factor=1.0,
                suggestion=suggestion,
                created_by=admin_id,
            )
            db.add(cs)
            added += 1

    await db.commit()
    print(f"  ✅ CapacitySnapshot +{added}")


# ═══════════════════════════════════════════════════════════════════
# 11. DailyReport(过去 30 天 × 全员每工作日 1 条)
# ═══════════════════════════════════════════════════════════════════

# 真实 raw_input_text 模板(模拟员工在企微群里发的口语化日报)
# 每个 (user_name, role) 对应 N 条候选,seed 时按 weekday 轮转 + 随机加细节
DAILY_REPORT_TEMPLATES = {
    "张毅": [
        {
            "raw": "今天主要做了 206 项目设备状态聚合接口,接口已经联调通过,郭震那边的前端可以并行了。\n"
            "卡点:压测发现并发 500 QPS 时数据库连接池打满,准备明天加连接池配置 + 排查慢 SQL。",
            "parsed": {
                "tasks": "完成 206 设备状态聚合接口开发 + 联调",
                "acceptance_criteria": "接口 P95 ≤ 200ms,前端可调通",
                "support_needed": "需要 DBA 协助调整生产连接池配置",
                "progress": 90,
                "reviewer": "技术部长",
                "git_version": "feat/p206-device-agg @ abc1234",
                "blocker": "压测 500 QPS 数据库连接池打满",
                "next_step": "加连接池配置,排查慢 SQL,加 Redis 缓存层",
                "eta": str(TODAY + timedelta(days=2)),
            },
            "ai_score": 88,
            "pass_check": True,
            "ai_comment": "日报结构完整,卡点描述具体且有可执行方案。建议下次补充连接池目标参数。",
            "management_alert": None,
        },
        {
            "raw": "智能仓储 UAT 用例梳理到 80%,发现旧版用例覆盖不到新调度算法,需要补 30+ 用例。\n"
            "今天和仓管沟通了一下,他们对反馈页面的字段需求确认了。",
            "parsed": {
                "tasks": "仓储 UAT 用例梳理 + 与仓管确认反馈页面字段",
                "acceptance_criteria": "用例覆盖新调度算法 + 字段对齐业务方需求",
                "support_needed": "无",
                "progress": 80,
                "reviewer": "技术部长",
                "git_version": "wip/uat-cases @ def5678",
                "blocker": "",
                "next_step": "明天补完 30+ 用例,周五开始执行",
                "eta": str(TODAY + timedelta(days=3)),
            },
            "ai_score": 85,
            "pass_check": True,
            "ai_comment": "进度清晰,与业务方协同有效。下次建议量化「30+ 用例」的覆盖维度。",
            "management_alert": None,
        },
    ],
    "郭震": [
        {
            "raw": "完成了 206 Web 控制台的设备列表 + 状态卡片页面,Mock 数据先跑通,等张毅接口好了直接切真数据。\n"
            "WebSocket 推送逻辑也搭好骨架了,明天上联调环境。",
            "parsed": {
                "tasks": "206 Web 控制台前端 + WebSocket 骨架",
                "acceptance_criteria": "设备列表分页 + 状态卡片实时刷新",
                "support_needed": "等待张毅接口",
                "progress": 75,
                "reviewer": "张毅",
                "git_version": "feat/p206-console @ ghi9012",
                "blocker": "",
                "next_step": "联调真数据 + WebSocket 接入",
                "eta": str(TODAY + timedelta(days=1)),
            },
            "ai_score": 84,
            "pass_check": True,
            "ai_comment": "清晰描述完成项与依赖项。建议补充并发推送的兜底策略。",
            "management_alert": None,
        },
    ],
    "新雷": [
        {
            "raw": "AI 故障预测模型 v0.3 接入完成,在历史数据上回测 F1 = 0.81。\n"
            "但是 P95 延迟还有 920ms,目标是 800ms,可能要做下批量推理 + 缓存。\n"
            "讯飞那边的 ASR 服务今天偶发 502,影响了语音日报的端到端测试。",
            "parsed": {
                "tasks": "AI 故障预测模型接入 + 回测 + ASR 联调",
                "acceptance_criteria": "F1 ≥ 0.8 且 P95 ≤ 800ms",
                "support_needed": "需要协调讯飞团队定位 502",
                "progress": 70,
                "reviewer": "技术部长",
                "git_version": "feat/p206-ai-fault @ jkl3456",
                "blocker": "讯飞 ASR 偶发 502,影响测试节奏",
                "next_step": "做批量推理优化 + 缓存层,讯飞服务异常找供应商",
                "eta": str(TODAY + timedelta(days=3)),
            },
            "ai_score": 87,
            "pass_check": True,
            "ai_comment": "数据指标清晰,卡点描述具体且对外升级。建议附上回测样本量。",
            "management_alert": "讯飞 ASR 偶发 502,影响 P2026-001 端到端测试。建议商务联系讯飞确认 SLA。",
        },
    ],
    "林跃文": [
        {
            "raw": "206 PCB v2 贴片样机回来 5 片,自检 4 片通过、1 片虚焊。\n"
            "找贴片厂返工,预计后天回件。等焊好之后郑韬慧那边马上跑测试。",
            "parsed": {
                "tasks": "PCB v2 样机入库 + 自检 + 虚焊返工",
                "acceptance_criteria": "5 片样机全部通过自检",
                "support_needed": "无",
                "progress": 80,
                "reviewer": "技术部长",
                "git_version": "",
                "blocker": "1 片 PCB 虚焊待返工",
                "next_step": "贴片厂返工 → 郑韬慧测试",
                "eta": str(TODAY + timedelta(days=2)),
            },
            "ai_score": 82,
            "pass_check": True,
            "ai_comment": "硬件进度描述具体,有数量化指标。建议下次注明虚焊故障类型。",
            "management_alert": None,
        },
    ],
    "郑韬慧": [
        {
            "raw": "今天对 206 的 4 片样机做了温度循环测试,3 片通过、1 片在 -20°C 出现重启。\n"
            "怀疑是电源滤波电容选型问题,已经反馈给林跃文。",
            "parsed": {
                "tasks": "206 样机温度循环测试",
                "acceptance_criteria": "工业温度区间 -20°C ~ +60°C 全程稳定",
                "support_needed": "等林跃文确认电容替换方案",
                "progress": 60,
                "reviewer": "技术部长",
                "git_version": "",
                "blocker": "1 片样机 -20°C 重启",
                "next_step": "等电容方案 → 重测",
                "eta": str(TODAY + timedelta(days=5)),
            },
            "ai_score": 89,
            "pass_check": True,
            "ai_comment": "故障描述精确(温度 + 现象 + 怀疑原因),具备工程师标准。",
            "management_alert": "206 样机低温稳定性存在隐患,可能影响 Gate 3 通过时间。",
        },
    ],
    "采购经理": [
        {
            "raw": "206 项目核心传感器 IC 货期更新:供应商承诺下周一到货,比原计划晚 3 天。\n"
            "电容、电阻物料已全部入库。",
            "parsed": {
                "tasks": "206 物料采购跟进",
                "acceptance_criteria": "Sprint 2 前所有物料到齐",
                "support_needed": "无",
                "progress": 85,
                "reviewer": "技术部长",
                "git_version": "",
                "blocker": "核心 IC 延迟 3 天",
                "next_step": "下周一到货后立即送贴片厂",
                "eta": str(TODAY + timedelta(days=4)),
            },
            "ai_score": 83,
            "pass_check": True,
            "ai_comment": "采购进度清晰,延迟有补救方案。",
            "management_alert": "206 核心 IC 延迟 3 天到货,可能压缩贴片厂窗口。",
        },
    ],
    "仓管": [
        {
            "raw": "今天对新调度系统的反馈页面提了 3 个改进:1.批量勾选;2.字段顺序按习惯调整;3.高频操作按钮放右下。\n"
            "已经和张毅过了,会在 Sprint 末优化。",
            "parsed": {
                "tasks": "仓储新系统体验反馈",
                "acceptance_criteria": "UI 流程符合一线作业习惯",
                "support_needed": "无",
                "progress": 100,
                "reviewer": "技术部长",
                "git_version": "",
                "blocker": "",
                "next_step": "等下个版本验证",
                "eta": str(TODAY + timedelta(days=7)),
            },
            "ai_score": 75,
            "pass_check": True,
            "ai_comment": "业务方反馈到位,反映出需求与开发的良性协同。",
            "management_alert": None,
        },
    ],
    "技术部长": [
        {
            "raw": "今天主要做了 Sprint 2 的 status check + 206 项目 Gate 3 准备工作梳理。\n"
            "把张毅、新雷的卡点都同步给采购经理,IC 延迟的事情让商务部联系供应商升级。",
            "parsed": {
                "tasks": "Sprint 2 跟踪 + Gate 3 准备",
                "acceptance_criteria": "Gate 3 提前 1 周完成所有验收材料",
                "support_needed": "商务部联系 IC 供应商",
                "progress": 65,
                "reviewer": "总经理",
                "git_version": "",
                "blocker": "IC 延迟可能影响 Gate 3 时间窗口",
                "next_step": "下周中评估是否需要调整 Gate 3 时间",
                "eta": str(TODAY + timedelta(days=7)),
            },
            "ai_score": 86,
            "pass_check": True,
            "ai_comment": "管理职责清晰,有提前介入风险的动作。",
            "management_alert": "建议总经理关注 206 Gate 3 时间窗口压力。",
        },
    ],
    "销售部长": [
        {
            "raw": "P2026-003 合同审核项目需求收集会议开了,客户给了 8 类典型合同样本。\n"
            "下周和新雷一起做 AI 方案的可行性论证。",
            "parsed": {
                "tasks": "P2026-003 需求收集 + 样本梳理",
                "acceptance_criteria": "完成立项 Gate 评审",
                "support_needed": "新雷协助 AI 方案设计",
                "progress": 40,
                "reviewer": "总经理",
                "git_version": "",
                "blocker": "",
                "next_step": "和新雷讨论 AI 方案可行性",
                "eta": str(TODAY + timedelta(days=10)),
            },
            "ai_score": 78,
            "pass_check": True,
            "ai_comment": "立项阶段动作合理,样本类型量化清晰。",
            "management_alert": None,
        },
    ],
    "财务部长": [
        {
            "raw": "Q2 预算执行率 51%,P2026-001 已用 145 万 / 280 万,符合节奏。\n" "贴片厂的发票本周到位。",
            "parsed": {
                "tasks": "Q2 预算盘点 + 发票跟进",
                "acceptance_criteria": "预算执行率与项目进度对齐",
                "support_needed": "无",
                "progress": 100,
                "reviewer": "总经理",
                "git_version": "",
                "blocker": "",
                "next_step": "下周开始 Q3 预算预编",
                "eta": str(TODAY + timedelta(days=14)),
            },
            "ai_score": 80,
            "pass_check": True,
            "ai_comment": "财务数据精确,预算节奏与项目对齐。",
            "management_alert": None,
        },
    ],
    "生产经理": [
        {
            "raw": "和林跃文对了 206 量产工艺评审的 checklist,有 3 项还需要硬件出工艺文件。",
            "parsed": {
                "tasks": "206 量产工艺评审准备",
                "acceptance_criteria": "工艺文件完整,可送评审",
                "support_needed": "林跃文出工艺文件",
                "progress": 50,
                "reviewer": "技术部长",
                "git_version": "",
                "blocker": "3 项工艺文件未交付",
                "next_step": "等林跃文补",
                "eta": str(TODAY + timedelta(days=5)),
            },
            "ai_score": 79,
            "pass_check": True,
            "ai_comment": "卡点描述清晰,具体到 3 项。",
            "management_alert": None,
        },
    ],
    "商务经理": [
        {
            "raw": "今天 P2026-003 项目的客户访谈做了 2 家,合同审核痛点主要在「条款比对」和「金额风险标记」上。",
            "parsed": {
                "tasks": "客户访谈 + 痛点梳理",
                "acceptance_criteria": "完成 5 家客户访谈",
                "support_needed": "无",
                "progress": 40,
                "reviewer": "销售部长",
                "git_version": "",
                "blocker": "",
                "next_step": "明天再访 2 家",
                "eta": str(TODAY + timedelta(days=3)),
            },
            "ai_score": 81,
            "pass_check": True,
            "ai_comment": "痛点量化具体,有助于产品需求定义。",
            "management_alert": None,
        },
    ],
    "陈思琪": [
        {
            "raw": "整理了 P2026-003 项目的 3 份样本合同,标了 6 处典型审核点。",
            "parsed": {
                "tasks": "样本合同标注",
                "acceptance_criteria": "20+ 审核点完整标注",
                "support_needed": "无",
                "progress": 30,
                "reviewer": "商务经理",
                "git_version": "",
                "blocker": "",
                "next_step": "继续标注剩余样本",
                "eta": str(TODAY + timedelta(days=4)),
            },
            "ai_score": 76,
            "pass_check": True,
            "ai_comment": "数据准备工作扎实。",
            "management_alert": None,
        },
    ],
    "总经理": [
        {
            "raw": "今天和技术部长、销售部长各对了一次 Q2 OKR 进展。206 项目压力较大,我个人会盯着 Gate 3 的关键路径。",
            "parsed": {
                "tasks": "Q2 OKR review + 206 Gate 3 介入",
                "acceptance_criteria": "Q2 末 206 通过 Gate 3",
                "support_needed": "无",
                "progress": 60,
                "reviewer": "(self-review)",
                "git_version": "",
                "blocker": "",
                "next_step": "每周固定 1 小时跟 206",
                "eta": str(TODAY + timedelta(days=14)),
            },
            "ai_score": 80,
            "pass_check": True,
            "ai_comment": "管理层视角清晰,有重点关注。",
            "management_alert": None,
        },
    ],
}


async def seed_daily_reports(db, admin_id):
    print("\n[11/12] DailyReport(过去 30 天 × 全员)…")
    # 拿所有员工(排除从未入职的)
    r = await db.execute(select(User))
    users = list(r.scalars())

    # ── V2.2: 预建 user_id → 项目列表 / 项目 → 任务列表 映射(回填日报关联)──
    # 1) user_id → 该用户参与的 project_id 列表(via project_members)
    user_projects: dict = {}
    pm_rows = await db.execute(select(ProjectMember.user_id, ProjectMember.project_id))
    for uid, pid in pm_rows.all():
        user_projects.setdefault(uid, []).append(pid)

    # 2) project_id → 该项目所有 sprint_task 列表(via sprint → tasks)
    project_tasks: dict = {}
    pt_rows = await db.execute(
        select(Sprint.project_id, SprintTask.id).join(SprintTask, SprintTask.sprint_id == Sprint.id)
    )
    for pid, tid in pt_rows.all():
        project_tasks.setdefault(pid, []).append(tid)

    workdays = workdays_between(DEMO_START, TODAY)
    added = 0
    relations_added = 0
    for u in users:
        templates = DAILY_REPORT_TEMPLATES.get(u.name)
        if not templates:
            # 没模板就跳过这个用户(避免造无意义日报)
            continue
        # 该员工参与的项目(用于回填 project_id)
        my_projects = user_projects.get(u.id, [])
        for wd in workdays:
            # 已存在 → skip
            existing = await db.execute(
                select(DailyReport).where(
                    DailyReport.user_id == u.id,
                    DailyReport.report_date == wd,
                )
            )
            if existing.scalar_one_or_none():
                continue

            # 选模板(按日期轮转,加点随机)
            tpl = templates[(wd.toordinal() + random.randint(0, 10)) % len(templates)]

            # 让 progress 随时间逐步增长(让趋势曲线好看)
            day_offset = (wd - DEMO_START).days  # 0 → 30
            progress_base = tpl["parsed"]["progress"]
            # 30 天前 progress = base - 30,今天 = base
            progress_adjusted = max(5, min(100, progress_base - (30 - day_offset)))

            parsed = dict(tpl["parsed"])
            parsed["progress"] = progress_adjusted

            # 分数随机波动 ±3
            score_jitter = tpl["ai_score"] + random.randint(-3, 3)
            score_jitter = max(60, min(100, score_jitter))

            # management_alert 只在 30% 的概率触发(避免每天都告警)
            alert = tpl["management_alert"] if random.random() < 0.3 else None

            # ── V2.2: 80% 概率挂项目,50% 概率再挂具体任务 ──
            project_id = None
            sprint_task_id = None
            if my_projects and random.random() < 0.8:
                project_id = random.choice(my_projects)
                relations_added += 1
                # 在选了项目的日报里,50% 概率从该项目任务库里挑一个
                proj_tasks = project_tasks.get(project_id, [])
                if proj_tasks and random.random() < 0.5:
                    sprint_task_id = random.choice(proj_tasks)

            report = DailyReport(
                user_id=u.id,
                report_date=wd,
                raw_input_text=tpl["raw"],
                media_urls=[],
                parsed_content=parsed,
                pass_check=tpl["pass_check"],
                reject_reason=None,
                suggested_guidance=None,
                ai_score=score_jitter,
                ai_comment=tpl["ai_comment"],
                management_alert=alert,
                mentioned_task_ids=[],
                project_id=project_id,
                sprint_task_id=sprint_task_id,
                created_by=admin_id,
            )
            db.add(report)
            added += 1

        # 每 1000 条 commit 一次,避免事务过大
        if added > 0 and added % 200 == 0:
            await db.commit()

    await db.commit()
    print(f"  ✅ DailyReport +{added}(其中 {relations_added} 条挂上了项目)")


# ═══════════════════════════════════════════════════════════════════
# 11.5 V2.3 临时工单项目示例(P2026-T01 日常支撑与临时工单)
# ═══════════════════════════════════════════════════════════════════

TEMP_PROJECT_CODE = "P2026-T01"
TEMP_PROJECT_NAME = "日常支撑与临时工单"
TEMP_PROJECT_DESC = "承载临时性 bug 修复、ERP 维护、改价工单等日常零散工作的轻量项目"

# 模拟员工挂在临时项目下的日报(覆盖 3 个员工 × 各 2-3 条,共 7 条)
TEMP_DAILY_REPORTS = [
    {
        "user_name": "张毅",
        "day_offset": -3,
        "raw": "今天救火处理 ERP 同步异常,排查到是订单状态推送时的字段映射改了,修了。后续把这个映射加上了校验。",
        "parsed": {
            "tasks": "ERP 订单同步异常修复 + 字段校验",
            "progress": 100,
            "blocker": "",
            "next_step": "明天值班期间继续观察 24h",
            "eta": str(TODAY),
        },
        "ai_score": 86,
    },
    {
        "user_name": "张毅",
        "day_offset": -8,
        "raw": "处理财务部紧急工单:对账单导出时间字段格式问题,临时打了热补丁。",
        "parsed": {
            "tasks": "财务对账单导出热补丁",
            "progress": 100,
            "blocker": "",
            "next_step": "下个版本统一时间字段处理",
            "eta": str(TODAY - timedelta(days=8)),
        },
        "ai_score": 81,
    },
    {
        "user_name": "郭震",
        "day_offset": -2,
        "raw": "改销售部反馈的价格规则:大客户阶梯折扣门槛从 50W 调到 30W,前后端都改了。",
        "parsed": {
            "tasks": "销售大客户阶梯折扣规则调整",
            "progress": 100,
            "blocker": "",
            "next_step": "下周观察一周折扣使用率",
            "eta": str(TODAY),
        },
        "ai_score": 83,
    },
    {
        "user_name": "郭震",
        "day_offset": -6,
        "raw": "处理 3 个临时工单:1.批量导出 PDF 报错;2.密码重置邮件英文乱码;3.列表分页参数遗漏。都修了。",
        "parsed": {
            "tasks": "批量修复 3 个用户反馈工单",
            "progress": 100,
            "blocker": "",
            "next_step": "无",
            "eta": str(TODAY - timedelta(days=6)),
        },
        "ai_score": 78,
    },
    {
        "user_name": "郭震",
        "day_offset": -10,
        "raw": "排查仓库部反馈的扫码慢问题,定位到是网关 nginx 默认超时太短,调整后从 15s 降到 3s。",
        "parsed": {
            "tasks": "扫码超时调优(nginx 超时配置)",
            "progress": 100,
            "blocker": "",
            "next_step": "把超时配置写进部署模板",
            "eta": str(TODAY - timedelta(days=10)),
        },
        "ai_score": 88,
    },
    {
        "user_name": "新雷",
        "day_offset": -4,
        "raw": "解决数据看板偶尔白屏的问题。发现是 token 过期后没自动刷新,加了一层拦截。",
        "parsed": {
            "tasks": "Dashboard token 过期自动刷新",
            "progress": 100,
            "blocker": "",
            "next_step": "看一周线上有没有再现",
            "eta": str(TODAY - timedelta(days=4)),
        },
        "ai_score": 85,
    },
    {
        "user_name": "新雷",
        "day_offset": -9,
        "raw": "临时帮采购部跑了一个 SQL 导数:近 90 天供应商交付准时率统计。结果发到他们邮箱了。",
        "parsed": {
            "tasks": "采购部一次性数据导出(交付准时率)",
            "progress": 100,
            "blocker": "",
            "next_step": "如果常用就建议加到报表中心",
            "eta": str(TODAY - timedelta(days=9)),
        },
        "ai_score": 76,
    },
]


async def seed_temp_projects(db, admin_id):
    """V2.3 临时工单项目示例数据(P2026-T01 + Backlog Sprint + 7 条日报)。

    幂等:按 code 唯一判重,已存在则跳过。
    支持 --only=temp_projects 单选。
    """
    print("\n[11.5/12] 临时工单项目示例(P2026-T01)…")

    # ── 1. 临时项目本体(is_temporary=True) ───────────────────
    existing = await db.execute(select(Project).where(Project.code == TEMP_PROJECT_CODE))
    proj = existing.scalar_one_or_none()
    if proj is None:
        proj = Project(
            code=TEMP_PROJECT_CODE,
            name=TEMP_PROJECT_NAME,
            description=TEMP_PROJECT_DESC,
            track=ProjectTrack.support,  # V2.3 Stage 2:日常支撑专用轨道
            current_stage=1,  # 临时项目不走 IPD 阶段,但字段必填,给个 1
            status=ProjectStatus.active,
            health_status=ProjectHealthStatus.green,
            health_score=100,
            planned_launch_date=None,
            budget_total=None,
            budget_spent=Decimal("0"),
            budget_alert_threshold=0.8,
            is_temporary=True,
            created_by=admin_id,
        )
        db.add(proj)
        await db.flush()
        print(f"  ✅ 临时项目 {TEMP_PROJECT_CODE} 已创建")
    else:
        print(f"  ⏭️  临时项目 {TEMP_PROJECT_CODE} 已存在,跳过")

    # ── 2. Backlog Sprint(sprint_number=0,作为日报下拉占位) ─
    existing_sp = await db.execute(
        select(Sprint).where(
            Sprint.project_id == proj.id,
            Sprint.sprint_number == 0,
        )
    )
    backlog = existing_sp.scalar_one_or_none()
    if backlog is None:
        backlog = Sprint(
            project_id=proj.id,
            stage_id=None,
            sprint_number=0,
            goal="Backlog (临时工单归集池)",
            start_date=TODAY,
            end_date=TODAY + timedelta(days=365),
            health_score=100,
            planned_story_points=0,
            completed_story_points=0,
            status=SprintStatus.active,
            created_by=admin_id,
        )
        db.add(backlog)
        await db.flush()
        print("  ✅ Backlog Sprint(sprint_number=0)已创建")
    else:
        print("  ⏭️  Backlog Sprint 已存在,跳过")

    # ── 3. 临时工单日报(挂 project_id=P2026-T01,sprint_task_id=None) ─
    added = 0
    for spec in TEMP_DAILY_REPORTS:
        uid = await get_user_id_by_name(db, spec["user_name"])
        if uid is None:
            print(f"    ⚠️  用户 '{spec['user_name']}' 不存在,跳过该日报")
            continue
        report_date = TODAY + timedelta(days=spec["day_offset"])
        # 幂等:按 (user_id, report_date, project_id) 判重
        existing_rpt = await db.execute(
            select(DailyReport).where(
                DailyReport.user_id == uid,
                DailyReport.report_date == report_date,
                DailyReport.project_id == proj.id,
            )
        )
        if existing_rpt.scalar_one_or_none():
            continue
        report = DailyReport(
            user_id=uid,
            report_date=report_date,
            raw_input_text=spec["raw"],
            media_urls=[],
            parsed_content=spec["parsed"],
            pass_check=True,
            ai_score=spec["ai_score"],
            ai_comment="临时工单(自动 seed)",
            management_alert=None,
            mentioned_task_ids=[],
            project_id=proj.id,
            sprint_task_id=None,  # 临时工单无任务挂钩
            created_by=admin_id,
        )
        db.add(report)
        added += 1

    await db.commit()
    print(f"  ✅ 临时工单日报 +{added}")


# ═══════════════════════════════════════════════════════════════════
# 12. RiskAlert(8 条管理层卡点)
# ═══════════════════════════════════════════════════════════════════


async def seed_risk_alerts(db, admin_id):
    print("\n[12/12] RiskAlert + KnowledgeItem…")
    # 找若干带 management_alert 的近期 daily_reports
    r = await db.execute(select(DailyReport).where(DailyReport.management_alert.isnot(None)).limit(20))
    reports_with_alerts = list(r.scalars())

    if not reports_with_alerts:
        print("  ⚠️  没有带 management_alert 的日报,跳过 risk_alert")
    else:
        added = 0
        for rpt in reports_with_alerts[:8]:
            existing = await db.execute(select(RiskAlert).where(RiskAlert.report_id == rpt.id))
            if existing.scalar_one_or_none():
                continue
            days_old = (TODAY - rpt.report_date).days
            status = "resolved" if days_old > 15 else ("escalated" if days_old > 7 else "unresolved")
            alert_type = "recurring" if days_old > 5 else "blocker"

            alert = RiskAlert(
                report_id=rpt.id,
                user_id=rpt.user_id,
                alert_type=alert_type,
                description=rpt.management_alert,
                material_code=None,
                po_number=None,
                status=status,
                days_unresolved=days_old if status != "resolved" else 0,
                resolved_at=(datetime.utcnow() - timedelta(days=days_old - 15) if status == "resolved" else None),
                created_by=admin_id,
            )
            db.add(alert)
            added += 1
        await db.commit()
        print(f"  ✅ RiskAlert +{added}")

    # ── KnowledgeItem(5 条,跨 5 个分类)─────────────────────
    KNOWLEDGE_ITEMS = [
        {
            "title": "如何写一份让 AI 高分的日报",
            "category": KnowledgeCategory.BEST_PRACTICE,
            "content": (
                "## 高分日报的 4 个要素\n\n"
                "1. **任务**:今天具体做了什么,**有动词**(开发完成 / 评审通过 / 联调 / 复盘)\n"
                "2. **进度**:0-100% 的整数,不要写「差不多」\n"
                "3. **验收标准**:对方怎么判定你这件事算完成\n"
                "4. **卡点 + 计划**:如果有卡点,**附下一步 + ETA**\n\n"
                "AI 评分参考徽远成 §3.2 日报评分细则,要素全 + 量化指标 = 85+ 分。\n"
            ),
            "tags": "日报,AI,评分,最佳实践",
        },
        {
            "title": "Gate 评审常见失败原因(经验教训)",
            "category": KnowledgeCategory.LESSON_LEARNED,
            "content": (
                "复盘 2025 年 4 个项目的 Gate 失败案例,根因分布:\n\n"
                "1. **接口未握手**(50%) — Gate 2 失败主因。Stage 2 末必须有跨轨「接口契约评审」\n"
                "2. **物料货期未确认**(25%) — 长货期物料(>4 周)的下单应在 Gate 1 通过后立刻启动\n"
                "3. **验收标准漂移**(15%) — Gate 入口标准与原立项不一致\n"
                "4. **关键路径任务缺资源**(10%) — Sprint 容量水位看板可以提前 1 周预判\n\n"
                "→ Gate 提前一周做「红绿黄」自评,绿色才申请正式评审。\n"
            ),
            "tags": "Gate,IPD,复盘,接口,物料",
        },
        {
            "title": "Sprint 回顾会模板",
            "category": KnowledgeCategory.TEMPLATE,
            "content": (
                "## Sprint 回顾会议模板(45 分钟)\n\n"
                "### 1. 数据回顾(10 min)\n"
                "- 计划 vs 完成 故事点\n"
                "- 燃尽图实际线 vs 理想线\n"
                "- 关键路径任务全部完成?\n\n"
                "### 2. 做对了什么(10 min)\n"
                "- 每人 1 个具体事件\n\n"
                "### 3. 可以改进什么(10 min)\n"
                "- 每人 1 个具体事件,**不指责个人**\n\n"
                "### 4. Action Items(15 min)\n"
                "- 必须有 owner + due date,纳入下个 Sprint backlog\n"
            ),
            "tags": "Sprint,回顾,模板,敏捷",
        },
        {
            "title": "FAQ:如何申请项目预算追加?",
            "category": KnowledgeCategory.FAQ,
            "content": (
                "**Q:项目预算执行率超过 80% 怎么办?**\n\n"
                "1. 系统会自动告警(`budget_alert_threshold=0.8`)\n"
                "2. 提交追加预算申请到 OA,**附上**:\n"
                "   - 剩余阶段成本预估\n"
                "   - 超支根因分析(物料涨价 / 工时超支 / 范围扩张)\n"
                "   - 收益变化评估\n"
                "3. ≤ 10% 追加由部长批准;> 10% 上总经理。\n"
            ),
            "tags": "预算,FAQ,流程",
        },
        {
            "title": "2025Q4 206 项目复盘报告",
            "category": KnowledgeCategory.RETROSPECTIVE,
            "content": (
                "## 206 项目 Q4 阶段复盘\n\n"
                "### 关键数据\n"
                "- Sprint 1-3 故事点完成率:88% / 92% / 84%\n"
                "- Gate 1/2 一次通过\n"
                "- 预算执行率 51%\n\n"
                "### 做对了\n"
                "- 软硬接口握手提前到 Stage 2 中段\n"
                "- AI 集成模块用 sidecar 方式,降低耦合\n\n"
                "### 教训\n"
                "- PCB v1 飞线问题占用 2 天返工 → 已加 DFM checklist\n"
                "- 讯飞 ASR 偶发 502 暴露供应商 SLA 风险 → 已启动备份方案评估\n"
            ),
            "tags": "复盘,206,Q4",
        },
    ]
    added_k = 0
    for spec in KNOWLEDGE_ITEMS:
        existing = await db.execute(select(KnowledgeItem).where(KnowledgeItem.title == spec["title"]))
        if existing.scalar_one_or_none():
            continue
        ki = KnowledgeItem(
            title=spec["title"],
            category=spec["category"],
            content=spec["content"],
            tags=spec["tags"],
            source_type="manual",
            view_count=random.randint(5, 80),
            helpful_count=random.randint(2, 25),
            created_by=admin_id,
        )
        db.add(ki)
        added_k += 1
    await db.commit()
    print(f"  ✅ KnowledgeItem +{added_k}")


# ═══════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════

ALL_MODULES = [
    ("users", seed_extra_users),
    ("projects", seed_projects_and_stages),
    ("gate_reviews", seed_gate_reviews),
    ("okr", seed_okr),
    ("sprints", seed_sprints_tasks_burndown),
    ("capacity", seed_capacity_snapshots),
    ("daily_reports", seed_daily_reports),
    ("temp_projects", seed_temp_projects),  # V2.3: 临时工单项目示例
    ("risk_alerts_and_knowledge", seed_risk_alerts),
]


async def reset_demo_data():
    """清空 demo 数据(保留 seed_admin 种的 8 个用户)."""
    print("\n⚠️  --reset:清空 demo 数据…")
    async with AsyncSessionLocal() as db:
        # 按外键依赖反向清理
        await db.execute(delete(BurndownSnapshot))
        await db.execute(delete(CapacitySnapshot))
        await db.execute(delete(SprintTask))
        await db.execute(delete(Sprint))
        await db.execute(delete(RiskAlert))
        await db.execute(delete(DailyReport))
        await db.execute(delete(KeyResult))
        await db.execute(delete(Objective))
        await db.execute(delete(OKRCycle))
        await db.execute(delete(GateReview))
        await db.execute(delete(ProjectMember))
        await db.execute(delete(ProjectStage))
        await db.execute(delete(Project))
        await db.execute(delete(KnowledgeItem))
        # 仅删 EXTRA_USERS,保留 seed_admin
        wechat_ids = [u["wechat_userid"] for u in EXTRA_USERS]
        await db.execute(delete(User).where(User.wechat_userid.in_(wechat_ids)))
        await db.commit()
    print("  ✅ 已清空 demo 数据(seed_admin 8 个用户保留)\n")


async def main(only: Optional[set], do_reset: bool):
    # 确保表存在(本机 dev 场景幂等建表)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    if do_reset:
        await reset_demo_data()

    # 拿 admin user id 当 created_by
    async with AsyncSessionLocal() as db:
        r = await db.execute(select(User).where(User.wechat_userid == "admin"))
        admin = r.scalar_one_or_none()
        if admin is None:
            print("❌ 没找到 admin 用户,请先跑 `python -m scripts.seed_admin`")
            return
        admin_id = admin.id

        for module_name, fn in ALL_MODULES:
            if only and module_name not in only:
                continue
            await fn(db, admin_id)

    print("\n" + "=" * 60)
    print("🎉 演示数据种子完成!")
    print("=" * 60)
    print("快速验证:")
    print("  uvicorn app.main:app --reload  # 启动后端")
    print("  cd frontend && npm run dev     # 启动前端")
    print("  访问 http://localhost:3000,使用 seed_admin.py 输出的临时密码登录")
    print("  Dashboard / 项目 / OKR / 资源水位 / 趋势 / AI 复盘 全部应有数据")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI-PM 演示数据种子")
    parser.add_argument("--reset", action="store_true", help="先清空 demo 数据再重种")
    parser.add_argument(
        "--only",
        type=str,
        default="",
        help=f"只跑指定模块,逗号分隔。可选:{','.join(m for m, _ in ALL_MODULES)}",
    )
    args = parser.parse_args()

    only_set = set(s.strip() for s in args.only.split(",") if s.strip()) if args.only else None
    if only_set:
        invalid = only_set - {m for m, _ in ALL_MODULES}
        if invalid:
            print(f"❌ 未知模块: {invalid}")
            sys.exit(1)

    print("🌱 AI-PM 演示数据种子开始…")
    print(f"  锚定日期 TODAY={TODAY}, 覆盖 [{DEMO_START} → {DEMO_END}]")
    asyncio.run(main(only_set, args.reset))
