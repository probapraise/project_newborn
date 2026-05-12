param(
    [Parameter(Mandatory=$true)][string]$Reason,
    [int]$DurationHours = 4,
    [switch]$DryRun
)

. "$PSScriptRoot\LifeOps.Common.ps1"

try {
    $python = Initialize-LifeOpsEnvironment
    $args = @('-m', 'lifeops.cli', 'enter-recovery-mode', '--reason', $Reason, '--duration-hours', $DurationHours)
    if ($DryRun) { $args += '--dry-run' }
    & $python @args
    exit $LASTEXITCODE
} catch {
    Write-LifeOpsLog "Enter-RecoveryMode.ps1 failed: $($_.Exception.Message)"
    Write-Host "Recovery mode failed: $($_.Exception.Message)"
    exit 1
}
