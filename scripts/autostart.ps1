# Resident 开机自启：先起 Resident，再起 NapCat（QQ 注入）
# 由计划任务以管理员身份执行（RunLevel Highest）

$ErrorActionPreference = "Continue"
$root = "C:\Users\asus\Documents\deepseek-harness\default-workspace\Resident"
$logDir = Join-Path $root "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$env:DEEPSEEK_API_KEY = [Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY', 'User')
$env:PYTHONUNBUFFERED = "1"
Set-Location $root

# 1) Resident（隐藏窗口，日志落文件；已有实例则跳过）
$already = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'main\.py' }
if (-not $already) {
    Start-Process -FilePath "python" -ArgumentList "-u", "main.py" `
        -WorkingDirectory $root -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $logDir "resident.log") `
        -RedirectStandardError (Join-Path $logDir "resident.err.log")
}

# 2) 等 Resident 占好 6700
Start-Sleep -Seconds 8

# 3) NapCat + QQ（本任务已是管理员，无需再提权）
$qq = Get-Process -Name QQ -ErrorAction SilentlyContinue
if (-not $qq) {
    Start-Process -FilePath "C:\NapCat\start_quick_admin.bat" -WorkingDirectory "C:\NapCat" -WindowStyle Hidden
}
