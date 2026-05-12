param(
    [Parameter(Mandatory=$true)][int]$EventId,
    [Parameter(Mandatory=$true)]
    [ValidateSet('return_now', 'intentional_rest', 'fatigue', 'health', 'overload', 'adjust_plan', 'false_positive')]
    [string]$Choice,
    [Nullable[int]]$DurationMinutes = $null,
    [string]$Reason = '',
    [switch]$EnterRecoveryMode,
    [int]$RecoveryDurationHours = 4,
    [switch]$RecoveryDryRun
)

. "$PSScriptRoot\LifeOps.Common.ps1"

try {
    $python = Initialize-LifeOpsEnvironment
    $args = @('-m', 'lifeops.cli', 'record-decision', '--event-id', $EventId, '--choice', $Choice)
    if ($null -ne $DurationMinutes) {
        $args += @('--duration-minutes', $DurationMinutes)
    }
    if ($Reason.Trim().Length -gt 0) {
        $args += @('--reason', $Reason)
    }
    if ($EnterRecoveryMode) {
        $args += @('--enter-recovery-mode', '--recovery-duration-hours', $RecoveryDurationHours)
        if ($RecoveryDryRun) {
            $args += '--recovery-dry-run'
        }
    }
    & $python @args
    exit $LASTEXITCODE
} catch {
    Write-LifeOpsLog "Record-InterventionDecision.ps1 failed: $($_.Exception.Message)"
    Write-Host "Decision recording failed: $($_.Exception.Message)"
    exit 1
}