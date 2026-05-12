param(
    [string]$CoreUrl = 'http://127.0.0.1:8765'
)

Set-StrictMode -Version Latest

$taskName = 'LifeOpsWslActivityBridge'
$ps = (Get-Command pwsh -ErrorAction SilentlyContinue)
if (-not $ps) {
    $ps = Get-Command powershell -ErrorAction Stop
}

$script = Join-Path $PSScriptRoot 'Run-ActivityBridge.ps1'
$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$script`" -CoreUrl `"$CoreUrl`""
$action = New-ScheduledTaskAction -Execute $ps.Source -Argument $argument
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Forward Chrome/Steam activity to LifeOps WSL core.' -Force | Out-Null
Write-Host "Installed startup task: $taskName"
