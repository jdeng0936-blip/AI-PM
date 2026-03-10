"""
模拟 7 人发日报 → Mock AI 解析 → 落库 → 前端可查看
"""
import httpx
import json

BASE = "http://127.0.0.1:8001"
TOKEN = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
         "eyJzdWIiOiJhMDAwMDAwMC0wMDAwLTAwMDAtMDAwMC0wMDAwMDAwMDAwMDEiLCJyb2xlIjoiYWRtaW4ifQ."
         "aDcsWW4bnStxSF6m3bIAUWKy8uemp9kVAzzJ2HX9ths")
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

# ── 7 人真实日报内容（模拟徽远成各部门员工每日汇报）──
DAILY_REPORTS = [
    {
        "wechat_userid": "wx_zhangyi",
        "raw_text": (
            "今日完成 AI-PM 前端监控台页面开发，含3个统计卡片、项目健康矩阵、风险阻碍池。\n"
            "使用 Vue 3 + Element Plus + Tailwind CSS 实现暗色主题，Axios 对接后端 API。\n"
            "完成进度：85%\n"
            "明日计划：甘特图交互优化 + 日报流页面联调\n"
            "代码已提交 git commit abc123"
        ),
    },
    {
        "wechat_userid": "wx_guozhen",
        "raw_text": (
            "今日任务：206样机主控板 PCB Layout 验证\n"
            "完成进度：70%\n"
            "验收标准：DRC 检查零报错 + 3D 碰撞检测通过\n"
            "卡点：等待林跃文确认电源模块选型，影响电源区域布线\n"
            "需要采购部确认 LDO 芯片交期，预计延期3天"
        ),
    },
    {
        "wechat_userid": "wx_linyuewen",
        "raw_text": (
            "采购进展：\n"
            "1. 与供应商A确认了MCU芯片价格，已下单100片样品\n"
            "2. 电源LDO芯片TI TPS63020还在比价中，三家供应商报价差异15%\n"
            "完成进度：60%\n"
            "卡点：TPS63020 供应商B说交期要4周，可能影响SMT排产\n"
            "建议切换备选方案 TPS63070，需要郭震确认兼容性"
        ),
    },
    {
        "wechat_userid": "wx_zhengtaohui",
        "raw_text": (
            "今天在搭建测试环境"
        ),
    },
    {
        "wechat_userid": "wx_taoqun",
        "raw_text": (
            "仓库今日工作汇报：\n"
            "1. 完成206项目物料入库清点：MCU x100, 电阻电容 x5000, PCB空板 x50\n"
            "2. 更新 ERP 库存台账，与采购对账无差异\n"
            "3. 整理了二楼仓库货架，腾出206专区\n"
            "完成进度：100%\n"
            "明日计划：准备SMT领料配套"
        ),
    },
    {
        "wechat_userid": "wx_chenjiayun",
        "raw_text": (
            "今日配合陶群完成物料入库和清点工作。\n"
            "完成进度：90%\n"
            "另外发现去年遗留的一批 ESD模块 还没有处理，是否需要报废？\n"
            "希望管理层尽快决策，占用了半个货架位"
        ),
    },
    {
        "wechat_userid": "wx_boss",
        "raw_text": (
            "今日主要工作：\n"
            "1. 参加206项目立项评审，确认IPD五阶段里程碑节点\n"
            "2. 与新华区政府对接技改补贴申报材料，预计4月提交\n"
            "3. review 了AI-PM系统前端看板，整体效果满意，提出数据大屏显示需求\n"
            "完成进度：80%\n"
            "明日重点：跟进客户样机交付时间表"
        ),
    },
]


def main():
    client = httpx.Client(base_url=BASE, headers=HEADERS, timeout=15)

    print("═" * 60)
    print("  模拟 7 人日报提交（Mock AI 引擎）")
    print("═" * 60)

    results = []
    for i, report in enumerate(DAILY_REPORTS, 1):
        r = client.post("/api/v1/simulate/daily-report", json=report)
        data = r.json()
        results.append(data)

        status = "✅ 通过" if data.get("pass_check") else "⚠️ 退回"
        score = data.get("ai_score", "-")
        name = data.get("user_name", "?")
        dept = data.get("department", "?")
        comment = data.get("ai_comment", "")
        alert = data.get("management_alert")

        print(f"\n  [{i}/7] {name}（{dept}）")
        print(f"    评分: {score}/100  {status}")
        print(f"    评语: {comment}")
        if alert:
            print(f"    🚨 预警: {alert}")

    # 汇总
    scores = [r.get("ai_score", 0) for r in results]
    passed = sum(1 for r in results if r.get("pass_check"))
    alerts_count = sum(1 for r in results if r.get("management_alert"))

    print(f"\n{'═' * 60}")
    print(f"  📊 汇总")
    print(f"{'═' * 60}")
    print(f"  提交人数: {len(results)}")
    print(f"  通过/退回: {passed}/{len(results) - passed}")
    print(f"  平均分: {sum(scores) / len(scores):.1f}")
    print(f"  最高分: {max(scores)} / 最低分: {min(scores)}")
    print(f"  预警数: {alerts_count}")
    print(f"{'═' * 60}")
    print(f"\n  👉 打开前端查看: http://127.0.0.1:5173/reports")
    print(f"  👉 Dashboard: http://127.0.0.1:5173/dashboard")


if __name__ == "__main__":
    main()
