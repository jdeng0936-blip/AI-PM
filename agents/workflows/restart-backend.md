---
description: 重启后端服务（先杀旧进程再启动新实例）
---

## 重启后端 uvicorn 服务

每次需要启动或重启后端服务时，**必须**按以下步骤执行，避免多个旧进程同时监听 8000 端口导致新代码不生效。

// turbo-all

1. 查找所有监听 8000 端口的进程：
```powershell
netstat -ano | findstr ":8000" | findstr "LISTEN"
```

2. 杀死所有监听 8000 端口的进程（将上一步输出的 PID 替换进去）：
```powershell
# 提取所有 PID 并批量杀死
$pids = (netstat -ano | findstr ":8000" | findstr "LISTEN") | ForEach-Object { ($_ -split '\s+')[-1] } | Sort-Object -Unique
if ($pids) { $pids | ForEach-Object { taskkill /F /PID $_ 2>$null }; echo "Killed PIDs: $pids" } else { echo "No old processes found" }
```

3. 等待 2 秒确保端口释放：
```powershell
Start-Sleep -Seconds 2
```

4. 启动新的 uvicorn 实例：
```powershell
cd d:\AIProject\AI_SalesForce\srisalesforce\backend
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

5. 验证只有一个进程监听 8000：
```powershell
netstat -ano | findstr ":8000" | findstr "LISTEN"
```
预期结果：只有 2 行（主进程 + reload worker），不应超过 2 行。
