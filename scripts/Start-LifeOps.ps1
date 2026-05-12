. "$PSScriptRoot\LifeOps.Common.ps1"

$root = Get-LifeOpsRepoRoot
Write-LifeOpsLog 'Start-LifeOps.ps1 started.'

try {
    $python = Initialize-LifeOpsEnvironment
} catch {
    Write-LifeOpsLog "Startup stopped: $($_.Exception.Message)"
    Show-LifeOpsNotification -Title 'LifeOps Codex' -Message 'Python 3.12+를 찾지 못했습니다. Python 설치 또는 LIFEOPS_PYTHON 설정이 필요합니다.'
    exit 1
}

& $python -m lifeops.cli init-db | Out-Null
& $python -m lifeops.cli export-boot-briefing-context --output (Join-Path $root 'data\exports\boot_briefing_context.md') | Out-Null

Start-LifeOpsManagedProcess -Name 'watcher' -ScriptPath (Join-Path $PSScriptRoot 'Run-Watcher.ps1')
Start-LifeOpsManagedProcess -Name 'dispatcher' -ScriptPath (Join-Path $PSScriptRoot 'Run-EventDispatcher.ps1')

& (Join-Path $PSScriptRoot 'Open-CodexOperator.ps1')
Write-LifeOpsLog 'Start-LifeOps.ps1 completed.'
