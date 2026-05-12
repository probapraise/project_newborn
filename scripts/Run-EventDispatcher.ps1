param(
    [int]$IntervalSeconds = 60,
    [switch]$DryRun,
    [switch]$Once
)

. "$PSScriptRoot\LifeOps.Common.ps1"
try {
    $python = Initialize-LifeOpsEnvironment
    Write-LifeOpsLog 'Run-EventDispatcher.ps1 entered.'
    $args = @('-m', 'lifeops.event_dispatcher', '--interval', $IntervalSeconds)
    if ($DryRun) { $args += '--dry-run' }
    if ($Once) { $args += '--once' }
    & $python @args
} catch {
    Write-LifeOpsLog "Run-EventDispatcher.ps1 stopped: $($_.Exception.Message)"
    exit 1
}
