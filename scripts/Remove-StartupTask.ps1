. "$PSScriptRoot\LifeOps.Common.ps1"

$taskName = 'LifeOpsCodexOperator'
$removed = $false

try {
    $existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if ($existing) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction Stop
        Write-LifeOpsLog "Removed startup task $taskName."
        Write-Host "Removed startup task: $taskName"
        $removed = $true
    }
} catch {
    Write-LifeOpsLog "Startup task removal failed: $($_.Exception.Message)"
    Write-Host "Startup task removal failed: $($_.Exception.Message)"
}

if (Remove-LifeOpsStartupLauncher) {
    Write-Host "Removed Startup folder launcher."
    $removed = $true
}

if (-not $removed) {
    Write-Host "Startup registration was not installed: $taskName"
}
