param(
    [ValidateSet('fatigue', 'health', 'overload', 'adjust_plan')]
    [string]$Choice = 'fatigue',
    [int]$DurationMinutes = 30,
    [int]$RecoveryDurationHours = 2,
    [switch]$RecoveryDryRun
)

. "$PSScriptRoot\LifeOps.Common.ps1"

try {
    $python = Initialize-LifeOpsEnvironment
    $args = @(
        '-m', 'lifeops.recovery_decision_self_check',
        '--choice', $Choice,
        '--duration-minutes', $DurationMinutes,
        '--recovery-duration-hours', $RecoveryDurationHours
    )
    if ($RecoveryDryRun) {
        $args += '--recovery-dry-run'
    }
    & $python @args
    exit $LASTEXITCODE
} catch {
    Write-LifeOpsLog "Test-RecoveryDecisionFlow.ps1 failed: $($_.Exception.Message)"
    Write-Host "Recovery decision self-check failed: $($_.Exception.Message)"
    exit 1
}