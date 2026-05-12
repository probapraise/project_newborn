. "$PSScriptRoot\LifeOps.Common.ps1"

$taskName = 'LifeOpsCodexOperator'
$ps = Get-LifeOpsPowerShell
$startScript = Join-Path $PSScriptRoot 'Start-LifeOps.ps1'
$argument = "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`""
$action = New-ScheduledTaskAction -Execute $ps -Argument $argument
$trigger = New-ScheduledTaskTrigger -AtLogOn
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$userId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

try {
    $principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited -ErrorAction Stop
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Start LifeOps Codex Operator at user logon.' -Force -ErrorAction Stop | Out-Null
    Write-LifeOpsLog "Installed startup task $taskName."
    Write-Host "Installed startup task: $taskName"
} catch {
    Write-LifeOpsLog "Scheduled task install failed; falling back to Startup folder launcher: $($_.Exception.Message)"
    $launcherPath = Install-LifeOpsStartupLauncher -PowerShellPath $ps -StartScript $startScript
    Write-Host "Scheduled task install failed, so Startup folder launcher was installed instead: $launcherPath"
}
