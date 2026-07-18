<#
.SYNOPSIS
    一键启动 SOP 智脑演示环境（后端 + 前端 + 浏览器打开）

.DESCRIPTION
    - 启动后端 FastAPI（无需 PostgreSQL / MinIO，Demo 模式）
    - 启动前端 Vite Dev Server
    - 等待服务就绪后打开浏览器

.EXAMPLE
    .\scripts\demo-up.ps1
#>

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
if (-not $ProjectRoot) { $ProjectRoot = Split-Path -Parent $PSScriptRoot }

# 回到项目根
Set-Location $ProjectRoot

Write-Host "=== SOP 智脑 Demo 一键启动 ===" -ForegroundColor Cyan
Write-Host ""

# ---- 检查依赖 ----
function Test-Command($cmd) {
    return [bool](Get-Command $cmd -ErrorAction SilentlyContinue)
}

if (-not (Test-Command "python")) {
    Write-Host "❌ 需要 Python，请先安装" -ForegroundColor Red; exit 1
}
if (-not (Test-Command "pnpm")) {
    Write-Host "❌ 需要 pnpm，请运行 npm install -g pnpm" -ForegroundColor Red; exit 1
}

# ---- 启动后端 ----
Write-Host "[1/3] 启动后端 FastAPI (Demo 模式，无需数据库)..." -ForegroundColor Yellow
$backendJob = Start-Job -ScriptBlock {
    Set-Location $using:ProjectRoot
    & python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --reload
}
Write-Host "      后端 PID: $($backendJob.Id)" -ForegroundColor DarkGray

# ---- 启动前端 ----
Write-Host "[2/3] 启动前端 Vite Dev Server..." -ForegroundColor Yellow
$frontendDir = Join-Path $ProjectRoot "frontend\workstation"
$frontendJob = Start-Job -ScriptBlock {
    Set-Location $using:frontendDir
    & pnpm dev --host 0.0.0.0
}
Write-Host "      前端 PID: $($frontendJob.Id)" -ForegroundColor DarkGray

# ---- 等待就绪 ----
Write-Host "[3/3] 等待服务就绪..." -ForegroundColor Yellow
$maxWait = 30
$waited = 0
while ($waited -lt $maxWait) {
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:8000/docs" -TimeoutSec 2 -ErrorAction Stop
        break
    } catch {
        Start-Sleep -Seconds 2
        $waited += 2
    }
}

Write-Host ""
Write-Host "✅ 服务已就绪！" -ForegroundColor Green
Write-Host "   后端 API:  http://localhost:8000/docs" -ForegroundColor White
Write-Host "   前端 UI:   http://localhost:5173" -ForegroundColor White
Write-Host "   SOP Demo:  http://localhost:8000/api/sop/demo" -ForegroundColor White
Write-Host "   FSM Demo:  http://localhost:8000/api/fsm/demo" -ForegroundColor White
Write-Host ""

# 打开浏览器
Start-Process "http://localhost:5173"

Write-Host "按 Ctrl+C 停止所有服务..." -ForegroundColor DarkGray
try {
    Wait-Job $backendJob, $frontendJob
} finally {
    Stop-Job $backendJob, $frontendJob -ErrorAction SilentlyContinue
    Remove-Job $backendJob, $frontendJob -Force -ErrorAction SilentlyContinue
    Write-Host "已停止所有服务" -ForegroundColor Yellow
}
