"""
tests/test_models_init.py — Model 注册完整性回归测试

历史教训(2026-05-25, V2.0 发版前):
  app/models/audit_log.py 定义了 __tablename__ = "audit_logs",但
  app/models/__init__.py 漏 import,导致 Base.metadata 不感知此表。
  随后任何 alembic revision --autogenerate 都会把 audit_logs 误判为
  孤儿表并生成 op.drop_table('audit_logs'),若误执行将丢失所有审计记录。

这个测试在 CI 阶段拦截同类问题:
  app/models/__init__.py 必须显式 import 每一个有 __tablename__ 的 model 文件。

注意:不能仅靠运行时 Base.metadata.tables 比对 — 因为 app.main → routers → models
的间接 import 链会让 metadata "看起来" 完整,但 alembic env.py 走的是
`import app.models` 直接路径,只认 __init__.py 显式 import。
"""

from __future__ import annotations

import ast
from pathlib import Path

MODELS_DIR = Path(__file__).resolve().parent.parent / "app" / "models"


def _files_declaring_tablename() -> dict[str, str]:
    """扫所有 model 文件 → {module_stem: tablename_value}。"""
    out: dict[str, str] = {}
    for py_file in MODELS_DIR.glob("*.py"):
        if py_file.name in {"__init__.py", "base_mixin.py"}:
            continue
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__tablename__":
                    v = node.value
                    if isinstance(v, ast.Constant) and isinstance(v.value, str):
                        out[py_file.stem] = v.value
    return out


def _modules_imported_in_init() -> set[str]:
    """用 AST 解析 __init__.py 实际的 `from app.models.X import ...` / `from .X import ...`,
    返回 {X} 集合 — 仅未被注释的真实 import 语句。"""
    init_path = MODELS_DIR / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        # 形如 from app.models.audit_log import AuditLog
        if node.module.startswith("app.models."):
            imported.add(node.module.split(".", 2)[2])
        # 形如 from .audit_log import AuditLog (level=1)
        elif node.level == 1 and node.module:
            imported.add(node.module)
    return imported


def test_models_init_imports_every_table_file():
    """__init__.py 必须 import 每一个声明了 __tablename__ 的 model 文件。

    若新增 model 文件忘了在 __init__.py 加 import,本测试爆红 —
    防止 alembic autogenerate 误判该表为孤儿表并生成 drop_table。
    """
    declared = _files_declaring_tablename()
    imported = _modules_imported_in_init()

    not_imported = sorted(set(declared.keys()) - imported)
    assert not not_imported, (
        "以下 model 模块定义了 __tablename__,但未被 app/models/__init__.py 真实 import:\n"
        + "".join(f"  - {stem}.py(__tablename__='{declared[stem]}')\n" for stem in not_imported)
        + "请在 __init__.py 加上:from app.models.<module> import <Class>\n"
        "(注意:被注释的 import 行不算)"
    )


def test_metadata_matches_declared_tablenames():
    """运行时 Base.metadata.tables 必须覆盖所有源码声明的 __tablename__。

    这是第二道防线:即使 __init__.py 导得对,也要确保 SQLAlchemy 真的注册成功
    (类继承 Base、表名无错字等)。
    """
    import app.models  # noqa: F401
    from app.database import Base

    declared = set(_files_declaring_tablename().values())
    registered = set(Base.metadata.tables.keys())

    missing = declared - registered
    assert not missing, (
        "以下 __tablename__ 在源码中声明,但未注册到 Base.metadata.tables:\n"
        f"  缺失:{sorted(missing)}\n"
        f"  已注册({len(registered)}):{sorted(registered)}\n"
    )
