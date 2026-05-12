param(
    [string]$Date = '',
    [string]$Output = ''
)

. "$PSScriptRoot\LifeOps.Common.ps1"

try {
    $python = Initialize-LifeOpsEnvironment
    $args = @('-m', 'lifeops.cli', 'write-daily-summary')
    if ($Date.Trim().Length -gt 0) {
        $args += @('--date', $Date)
    }
    if ($Output.Trim().Length -gt 0) {
        $args += @('--output', $Output)
    }
    & $python @args
    exit $LASTEXITCODE
} catch {
    Write-LifeOpsLog "Run-DailySummary.ps1 failed: $($_.Exception.Message)"
    Write-Host "Daily summary failed: $($_.Exception.Message)"
    exit 1
}