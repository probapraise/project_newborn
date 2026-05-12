param(
    [int]$IntervalSeconds = 60,
    [switch]$Once
)

. "$PSScriptRoot\LifeOps.Common.ps1"
try {
    $python = Initialize-LifeOpsEnvironment
    Write-LifeOpsLog 'Run-Watcher.ps1 entered.'
    $args = @('-m', 'lifeops.activity_watcher', '--interval', $IntervalSeconds)
    if ($Once) { $args += '--once' }
    & $python @args
} catch {
    Write-LifeOpsLog "Run-Watcher.ps1 stopped: $($_.Exception.Message)"
    exit 1
}
