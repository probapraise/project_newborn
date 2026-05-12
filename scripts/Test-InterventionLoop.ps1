param(
    [string]$Choice = 'return_now',
    [Nullable[int]]$DurationMinutes = $null,
    [string]$Reason = 'LifeOps intervention loop self-check',
    [switch]$KeepArtifacts,
    [switch]$CleanupOnly
)

. "$PSScriptRoot\LifeOps.Common.ps1"

try {
    $python = Initialize-LifeOpsEnvironment
    if ($CleanupOnly) {
        $args = @('-m', 'lifeops.intervention_self_check', '--cleanup-only')
    } else {
        $args = @('-m', 'lifeops.intervention_self_check', '--choice', $Choice, '--reason', $Reason)
        if ($null -ne $DurationMinutes) {
            $args += @('--duration-minutes', $DurationMinutes)
        }
        if ($KeepArtifacts) {
            $args += @('--keep-artifacts')
        }
    }
    & $python @args
    exit $LASTEXITCODE
} catch {
    Write-LifeOpsLog "Test-InterventionLoop.ps1 failed: $($_.Exception.Message)"
    Write-Host "Intervention loop self-check failed: $($_.Exception.Message)"
    exit 1
}
