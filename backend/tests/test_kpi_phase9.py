"""
tests/test_kpi_phase9.py — Phase 9 KPI 后端三层测试

覆盖:
  - Model 层: UNIQUE NULLS NOT DISTINCT + Enum 校验
  - Service 层: upsert UPDATE 路径 / achievement no_data / list 排序
  - Router 层: admin 200 / employee 403 / 参数 422 / 入参 422
"""

from __future__ import annotations

import uuid
from importlib import import_module
from typing import Any, AsyncGenerator, cast

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import get_db
from app.middleware.rbac import create_access_token
from app.models.kpi_target import KpiMetric, KpiPeriod, KpiScope, KpiTarget
from app.models.user import User, UserRole
from app.schemas.kpi import KpiTargetIn
from app.services.kpi_service import calculate_kpi_achievement, list_kpi_targets, upsert_kpi_target

TEST_DATABASE_URL = settings.database_url.replace("/aipm_db", "/aipm_db_test")


async def _cleanup_kpi_test_data(db: AsyncSession) -> None:
    await db.execute(delete(KpiTarget))
    await db.execute(delete(User).where(User.wechat_userid.like("kpi_%")))


async def _ensure_analytics_views(db: AsyncSession) -> None:
    weekly_exists = (
        await db.execute(text("SELECT to_regclass('public.mv_weekly_dept_stats') IS NOT NULL"))
    ).scalar_one()
    daily_exists = (await db.execute(text("SELECT to_regclass('public.mv_daily_user_stats') IS NOT NULL"))).scalar_one()
    if weekly_exists and daily_exists:
        return

    await db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_weekly_dept_stats CASCADE"))
    await db.execute(text("DROP MATERIALIZED VIEW IF EXISTS mv_daily_user_stats CASCADE"))
    await db.execute(
        text(
            """
            CREATE MATERIALIZED VIEW mv_daily_user_stats AS
            SELECT
                dr.tenant_id,
                dr.user_id,
                u.name AS user_name,
                u.department,
                dr.report_date,
                COUNT(dr.id)::integer AS report_count,
                ROUND(AVG(dr.ai_score)::numeric, 2) AS avg_score,
                MAX(dr.ai_score) AS max_score,
                MIN(dr.ai_score) AS min_score,
                (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::integer AS pass_count,
                BOOL_OR(dr.pass_check IS TRUE) AS pass_check,
                TRUE AS submitted,
                MAX(dr.created_at) AS last_submitted_at,
                0::numeric AS submit_delay_minutes
            FROM daily_reports dr
            JOIN users u ON u.id = dr.user_id
            WHERE u.is_active = TRUE
              AND dr.deleted_at IS NULL
            GROUP BY dr.tenant_id, dr.user_id, u.name, u.department, dr.report_date
            WITH DATA
            """
        )
    )
    await db.execute(
        text(
            """
            CREATE MATERIALIZED VIEW mv_weekly_dept_stats AS
            SELECT
                dr.tenant_id,
                u.department,
                DATE_TRUNC('week', dr.report_date::timestamp)::date AS week_start,
                COUNT(dr.id)::integer AS total_reports,
                COUNT(DISTINCT dr.user_id)::integer AS active_users,
                du.total_users,
                ROUND(AVG(dr.ai_score)::numeric, 2) AS avg_score,
                (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::integer AS pass_count,
                ROUND(
                    (
                        (COUNT(*) FILTER (WHERE dr.pass_check IS TRUE))::numeric
                        / NULLIF(COUNT(dr.id), 0)
                        * 100
                    ),
                    2
                ) AS pass_rate,
                ROUND(
                    (
                        COUNT(DISTINCT dr.user_id)::numeric
                        / NULLIF(du.total_users, 0)
                        * 100
                    ),
                    2
                ) AS submitter_rate
            FROM daily_reports dr
            JOIN users u ON u.id = dr.user_id
            JOIN (
                SELECT tenant_id, department, COUNT(*)::integer AS total_users
                FROM users
                WHERE is_active = TRUE
                GROUP BY tenant_id, department
            ) du ON du.tenant_id = dr.tenant_id AND du.department = u.department
            WHERE u.is_active = TRUE
              AND dr.deleted_at IS NULL
            GROUP BY
                dr.tenant_id,
                u.department,
                DATE_TRUNC('week', dr.report_date::timestamp)::date,
                du.total_users
            WITH DATA
            """
        )
    )


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """本地 fixture:engine 在 test 自己的 event loop 内构造,
    规避 conftest 全局 db_session 与 pytest-asyncio 1.x loop_scope 不对齐的问题。
    """
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        await _cleanup_kpi_test_data(session)
        await _ensure_analytics_views(session)
        await session.commit()
        try:
            yield session
        finally:
            await session.rollback()
            await _cleanup_kpi_test_data(session)
            await session.commit()
    await engine.dispose()


async def _make_user(db: AsyncSession, role: UserRole, name: str = "KPI 测试用户") -> User:
    user = User(
        id=uuid.uuid4(),
        wechat_userid=f"kpi_{uuid.uuid4().hex[:12]}",
        name=name,
        department="技术部",
        job_title="工程师",
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id), user.role.value)}"}


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _get_test_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app = import_module("app.main").app
    test_app.dependency_overrides[get_db] = _get_test_db
    transport = ASGITransport(app=cast(Any, test_app))
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_unique_null_scope_value_blocks_duplicate(db_session: AsyncSession) -> None:
    """UNIQUE NULLS NOT DISTINCT - 同 (global, NULL, submit_rate, monthly) 第二次插入必须 IntegrityError"""
    db_session.add(
        KpiTarget(
            scope=KpiScope.global_,
            scope_value=None,
            metric=KpiMetric.submit_rate,
            target_value=95.0,
            period=KpiPeriod.monthly,
            tenant_id="default",
        )
    )
    await db_session.commit()
    db_session.add(
        KpiTarget(
            scope=KpiScope.global_,
            scope_value=None,
            metric=KpiMetric.submit_rate,
            target_value=99.0,
            period=KpiPeriod.monthly,
            tenant_id="default",
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_invalid_enum_value_rejected(db_session: AsyncSession) -> None:
    """非法 Enum 值(如 scope='unknown')必须被 PG 拒绝"""
    with pytest.raises((DBAPIError, IntegrityError)):
        await db_session.execute(
            text(
                "INSERT INTO kpi_targets (scope, scope_value, metric, target_value, period, tenant_id) "
                "VALUES ('unknown', NULL, 'submit_rate', 50.0, 'monthly', 'default')"
            )
        )
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_upsert_updates_existing_row(db_session: AsyncSession) -> None:
    """upsert 同 key 第二次写必须走 UPDATE, id 复用, 总行数不变"""
    actor = await _make_user(db_session, UserRole.admin, "KPI Admin")
    payload = KpiTargetIn(
        scope=KpiScope.global_,
        scope_value=None,
        metric=KpiMetric.submit_rate,
        target_value=80.0,
        period=KpiPeriod.monthly,
    )
    first = await upsert_kpi_target(db_session, payload, actor)
    payload2 = KpiTargetIn(
        scope=KpiScope.global_,
        scope_value=None,
        metric=KpiMetric.submit_rate,
        target_value=90.0,
        period=KpiPeriod.monthly,
    )
    second = await upsert_kpi_target(db_session, payload2, actor)
    row_count = (
        await db_session.execute(
            select(func.count())
            .select_from(KpiTarget)
            .where(
                KpiTarget.scope == KpiScope.global_,
                KpiTarget.scope_value.is_(None),
                KpiTarget.metric == KpiMetric.submit_rate,
                KpiTarget.period == KpiPeriod.monthly,
                KpiTarget.tenant_id == "default",
            )
        )
    ).scalar_one()

    assert first.id == second.id, "upsert 必须走 UPDATE 路径 (同 id)"
    assert second.target_value == 90.0
    assert row_count == 1


@pytest.mark.asyncio
async def test_calculate_achievement_no_data_returns_none(db_session: AsyncSession) -> None:
    """Phase 7 MV 无 blocker_resolve_days 聚合源, actual 必须 None / status='no_data'"""
    actor = await _make_user(db_session, UserRole.admin)
    await upsert_kpi_target(
        db_session,
        KpiTargetIn(
            scope=KpiScope.global_,
            scope_value=None,
            metric=KpiMetric.blocker_resolve_days,
            target_value=3.0,
            period=KpiPeriod.monthly,
        ),
        actor,
    )

    resp = await calculate_kpi_achievement(db_session, KpiPeriod.monthly)
    row = next(r for r in resp.rows if r.metric == KpiMetric.blocker_resolve_days)
    assert row.actual_value is None
    assert row.gap is None
    assert row.achievement_rate is None
    assert row.status == "no_data"


@pytest.mark.asyncio
async def test_list_kpi_targets_stable_order(db_session: AsyncSession) -> None:
    """list_kpi_targets 返回顺序按 (scope, metric, scope_value NULLS FIRST) 稳定"""
    actor = await _make_user(db_session, UserRole.admin)
    for payload in [
        KpiTargetIn(
            scope=KpiScope.department,
            scope_value="技术部",
            metric=KpiMetric.avg_score,
            target_value=80,
            period=KpiPeriod.monthly,
        ),
        KpiTargetIn(
            scope=KpiScope.global_,
            scope_value=None,
            metric=KpiMetric.submit_rate,
            target_value=95,
            period=KpiPeriod.monthly,
        ),
        KpiTargetIn(
            scope=KpiScope.global_,
            scope_value=None,
            metric=KpiMetric.avg_score,
            target_value=75,
            period=KpiPeriod.monthly,
        ),
    ]:
        await upsert_kpi_target(db_session, payload, actor)

    rows = await list_kpi_targets(db_session)
    global_indexes = [i for i, row in enumerate(rows) if row.scope == KpiScope.global_]
    dept_indexes = [i for i, row in enumerate(rows) if row.scope == KpiScope.department]
    assert global_indexes and dept_indexes
    assert max(global_indexes) < min(dept_indexes), "global scope 必须排在 department 之前"


@pytest.mark.asyncio
async def test_router_admin_get_returns_200(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _make_user(db_session, UserRole.admin, "ADM")
    response = await client.get("/api/v1/admin/kpi/", headers=_headers(admin))
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_router_employee_forbidden(client: AsyncClient, db_session: AsyncSession) -> None:
    employee = await _make_user(db_session, UserRole.employee, "EMP")
    response = await client.get("/api/v1/admin/kpi/", headers=_headers(employee))
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_router_invalid_period_returns_422(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _make_user(db_session, UserRole.admin)
    response = await client.get(
        "/api/v1/admin/kpi/achievement",
        params={"period": "daily"},
        headers=_headers(admin),
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_router_post_invalid_payload_returns_422(client: AsyncClient, db_session: AsyncSession) -> None:
    admin = await _make_user(db_session, UserRole.admin)
    response = await client.post(
        "/api/v1/admin/kpi/",
        headers=_headers(admin),
        json={
            "scope": "global",
            "scope_value": "X",
            "metric": "submit_rate",
            "target_value": 95.0,
            "period": "monthly",
        },
    )
    assert response.status_code == 422
