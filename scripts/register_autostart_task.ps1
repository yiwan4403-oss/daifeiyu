# 注册开机自启任务（需管理员运行）
$taskName = 'Resident-Autostart'
$script = 'C:\Users\asus\Documents\deepseek-harness\default-workspace\Resident\scripts\autostart.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`""
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 2 -RestartInterval ([TimeSpan]::FromMinutes(5))
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "REGISTERED: $taskName"
Get-ScheduledTask -TaskName $taskName | Select-Object TaskName, State
