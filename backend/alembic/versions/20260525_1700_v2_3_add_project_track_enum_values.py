"""V2.3: 给 projecttrack 枚举加 support / other 两个值(临时工单专用轨道)

背景:
  V2.3 Stage 1 落地后,临时工单项目都被默认建成 track=software,语义不准。
  新增 ProjectTrack.support(日常支撑)和 ProjectTrack.other(其它临时),
  专给 is_temporary=true 的项目使用,与主干 dual/software/hardware 严格分隔。

变更:
  - PostgreSQL 枚举类型 projecttrack 追加值 'support' 和 'other'
  - 使用 IF NOT EXISTS 保证本地开发已手工 ALTER TYPE 过的环境再跑也无害

设计说明:
  - PostgreSQL 在 9.6 之前 ADD VALUE 必须独占事务,从 12 开始支持事务内 ADD,
    但 alembic 默认事务 DDL 仍可能与某些 PG 版本不兼容。最稳妥用
    autocommit_block 显式跳出事务执行 ADD VALUE
  - downgrade 留空:PostgreSQL 不支持 DROP VALUE FROM ENUM;若需移除,只能
    重建类型并迁移数据,本 migration 不承担这个复杂度

幂等保护:
  - IF NOT EXISTS 自带幂等

Revision ID: b2c4d8e9f102
Revises: a1f3b7c2d801
Create Date: 2026-05-25 17:00:00.000000+08:00
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c4d8e9f102"
down_revision: Union[str, None] = "a1f3b7c2d801"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """幂等 upgrade — 枚举值已存在则跳过(IF NOT EXISTS)。"""
    # ADD VALUE 必须跳出事务执行,否则在某些 PG 配置下会报
    #   "ALTER TYPE ... ADD cannot run inside a transaction block"
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE projecttrack ADD VALUE IF NOT EXISTS 'support'")
        op.execute("ALTER TYPE projecttrack ADD VALUE IF NOT EXISTS 'other'")


def downgrade() -> None:
    """PostgreSQL 不支持 DROP VALUE FROM ENUM,降级无操作。

    如确需移除,需手动:
      1. 把使用该值的所有行改成其它值
      2. CREATE TYPE projecttrack_new AS ENUM (...保留的值...)
      3. ALTER TABLE projects ALTER COLUMN track TYPE projecttrack_new USING ...
      4. DROP TYPE projecttrack;ALTER TYPE projecttrack_new RENAME TO projecttrack
    本 migration 不承担这个复杂度。
    """
    pass
