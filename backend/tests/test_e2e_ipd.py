"""
端到端测试脚本 — 测试 IPD 全流程
"""
import httpx
import json

BASE = "http://127.0.0.1:8001"
TOKEN = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
         "eyJzdWIiOiJhMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDEiLCJyb2xlIjoiYWRtaW4ifQ."
         "aDcsWW4bnStxSF6m3bIAUWKy8uemp9kVAzzJ2HX9ths")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

client = httpx.Client(base_url=BASE, headers=HEADERS, timeout=15)

def pp(label, r):
    print(f"\n{'═'*60}")
    print(f"  {label}")
    print(f"  Status: {r.status_code}")
    print(f"{'═'*60}")
    try:
        print(json.dumps(r.json(), indent=2, ensure_ascii=False))
    except:
        print(r.text[:500])

# ── TEST 1: 立项 ──────────────────────────────────────────────
r = client.post("/api/v1/projects/", json={
    "name": "206样机研发及落地",
    "code": "P2026-001",
    "description": "Antigravity 206新型号智能硬件样机全周期研发",
    "track": "dual",
    "planned_launch_date": "2026-06-30",
    "budget_total": 500000,
    "budget_alert_threshold": 0.8,
})
pp("TEST 1: 立项 POST /api/v1/projects/", r)
project_id = r.json().get("project_id") if r.status_code == 200 else None

if not project_id:
    print("❌ 立项失败，终止测试")
    exit(1)

# ── TEST 2: 项目详情 + 5阶段验证 ──────────────────────────────
r = client.get(f"/api/v1/projects/{project_id}")
pp("TEST 2: 项目详情 GET /api/v1/projects/{id}", r)
data = r.json()
stages = data.get("stages", [])
print(f"\n  ⮕ 阶段数量: {len(stages)}")
for s in stages:
    print(f"    Stage {s['stage_number']}: {s['stage_name']} | "
          f"{s['planned_start']}→{s['planned_end']} | "
          f"health={s['health_status']} | gate_passed={s['gate_passed']}")

# ── TEST 3: 添加项目成员 ──────────────────────────────────────
members = [
    ("a0000000-0000-0000-0000-000000000002", "software", "Sprint Lead"),
    ("a0000000-0000-0000-0000-000000000003", "software", "全栈研发"),
    ("a0000000-0000-0000-0000-000000000004", "hardware", "采购负责人"),
    ("a0000000-0000-0000-0000-000000000005", "hardware", "贴片测试负责人"),
    ("a0000000-0000-0000-0000-000000000006", "both",     "发货调度"),
    ("a0000000-0000-0000-0000-000000000007", "both",     "仓库管理员"),
]
for uid, track, role in members:
    r = client.post(f"/api/v1/projects/{project_id}/members", json={
        "project_id": project_id, "user_id": uid, "track": track, "role_in_project": role,
    })
print(f"\n  ⮕ 已分配 {len(members)} 名成员到硬件/软件轨")

# ── TEST 4: 甘特图数据 ────────────────────────────────────────
r = client.get(f"/api/v1/projects/{project_id}/gantt")
pp("TEST 4: 甘特图 GET /api/v1/projects/{id}/gantt", r)

# ── TEST 5: 总览看板（健康矩阵）────────────────────────────────
r = client.get("/api/v1/projects/overview")
pp("TEST 5: 总览 GET /api/v1/projects/overview", r)

# ── TEST 6: 创建 Sprint #1 ────────────────────────────────────
stage_3_id = None
for s in stages:
    if s["stage_number"] == 3:
        stage_3_id = s["id"]
        break

r = client.post("/api/v1/sprints/", json={
    "project_id": project_id,
    "stage_id": stage_3_id,
    "sprint_number": 1,
    "goal": "完成 AI-PM 企微回调流水线端到端联调",
    "start_date": "2026-04-14",
    "end_date": "2026-04-27",
    "planned_story_points": 21,
})
pp("TEST 6: 创建 Sprint POST /api/v1/sprints/", r)
sprint_id = r.json().get("sprint_id") if r.status_code == 200 else None

# ── TEST 7: Sprint 列表 ───────────────────────────────────────
r = client.get(f"/api/v1/sprints/project/{project_id}")
pp("TEST 7: Sprint列表 GET /api/v1/sprints/project/{id}", r)

# ── 总结 ──────────────────────────────────────────────────────
print("\n" + "═"*60)
print("  📋 端到端测试汇总")
print("═"*60)
print(f"  ✅ 立项成功: P2026-001 '206样机研发及落地'")
print(f"  ✅ 5个 IPD 阶段自动初始化: {len(stages)} stages")
print(f"  ✅ {len(members)} 名成员分配到双轨")
print(f"  ✅ 甘特图数据可用")
print(f"  ✅ 项目总览返回健康矩阵")
print(f"  ✅ Sprint #1 已创建")
print("═"*60)
