param(
    [switch]$CheckScheduledTask,
    [switch]$SkipCodexCheck
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot\LifeOps.Common.ps1"

$results = New-Object System.Collections.Generic.List[object]
$failures = 0

function Add-StartupCheckResult {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][ValidateSet('PASS','WARN','FAIL')][string]$Status,
        [string]$Detail = ''
    )

    $script:results.Add([ordered]@{
        name = $Name
        status = $Status
        detail = $Detail
    }) | Out-Null

    if ($Status -eq 'FAIL') { $script:failures += 1 }
    Write-Host "[$Status] $Name $Detail"
    Write-LifeOpsLog "Startup check [$Status] $Name $Detail"
}

function Invoke-StartupExternalCheck {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$FilePath,
        [Parameter(Mandatory=$true)][string[]]$Arguments
    )

    try {
        $global:LASTEXITCODE = 0
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $global:LASTEXITCODE
        if ($exitCode -ne 0) {
            $detail = ($output | Out-String).Trim()
            if (-not $detail) { $detail = "exit code $exitCode" }
            Add-StartupCheckResult -Name $Name -Status 'FAIL' -Detail $detail
            return $false
        }
        Add-StartupCheckResult -Name $Name -Status 'PASS' -Detail ($FilePath + ' ' + ($Arguments -join ' '))
        return $true
    } catch {
        Add-StartupCheckResult -Name $Name -Status 'FAIL' -Detail $_.Exception.Message
        return $false
    }
}

$root = Get-LifeOpsRepoRoot
$runtimeDir = Join-Path $root 'data\runtime'
$exportDir = Join-Path $root 'data\exports'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
New-Item -ItemType Directory -Path $exportDir -Force | Out-Null

Write-LifeOpsLog 'Test-StartupFlow.ps1 started.'
Add-StartupCheckResult -Name 'repo_root' -Status 'PASS' -Detail $root

try {
    $ps = Get-LifeOpsPowerShell
    Add-StartupCheckResult -Name 'powershell' -Status 'PASS' -Detail $ps
} catch {
    Add-StartupCheckResult -Name 'powershell' -Status 'FAIL' -Detail $_.Exception.Message
    $ps = $null
}

try {
    $python = Initialize-LifeOpsEnvironment
    Add-StartupCheckResult -Name 'python_environment' -Status 'PASS' -Detail $python
} catch {
    Add-StartupCheckResult -Name 'python_environment' -Status 'FAIL' -Detail $_.Exception.Message
    $python = $null
}

if ($python) {
    Invoke-StartupExternalCheck -Name 'init_db' -FilePath $python -Arguments @('-m', 'lifeops.cli', 'init-db') | Out-Null

    $bootContext = Join-Path $exportDir 'boot_briefing_context.md'
    if (Invoke-StartupExternalCheck -Name 'boot_context' -FilePath $python -Arguments @('-m', 'lifeops.cli', 'export-boot-briefing-context', '--output', $bootContext)) {
        if ((Test-Path -LiteralPath $bootContext) -and ((Get-Item -LiteralPath $bootContext).Length -gt 0)) {
            Add-StartupCheckResult -Name 'boot_context_file' -Status 'PASS' -Detail $bootContext
        } else {
            Add-StartupCheckResult -Name 'boot_context_file' -Status 'FAIL' -Detail 'file missing or empty'
        }
    }

    $bootPrompt = Join-Path $exportDir 'boot_prompt.md'
    if (Invoke-StartupExternalCheck -Name 'boot_prompt' -FilePath $python -Arguments @('-m', 'lifeops.cli', 'write-boot-prompt', '--output', $bootPrompt)) {
        if ((Test-Path -LiteralPath $bootPrompt) -and ((Get-Item -LiteralPath $bootPrompt).Length -gt 0)) {
            Add-StartupCheckResult -Name 'boot_prompt_file' -Status 'PASS' -Detail $bootPrompt
        } else {
            Add-StartupCheckResult -Name 'boot_prompt_file' -Status 'FAIL' -Detail 'file missing or empty'
        }
    }
}

if ($ps -and $python) {
    $watcherScript = Join-Path $PSScriptRoot 'Run-Watcher.ps1'
    Invoke-StartupExternalCheck -Name 'watcher_once' -FilePath $ps -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $watcherScript, '-IntervalSeconds', '1', '-Once') | Out-Null

    $dispatcherScript = Join-Path $PSScriptRoot 'Run-EventDispatcher.ps1'
    Invoke-StartupExternalCheck -Name 'dispatcher_once_dry_run' -FilePath $ps -Arguments @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $dispatcherScript, '-IntervalSeconds', '1', '-Once', '-DryRun') | Out-Null
} elseif ($ps) {
    Add-StartupCheckResult -Name 'watcher_once' -Status 'WARN' -Detail 'skipped because python_environment failed'
    Add-StartupCheckResult -Name 'dispatcher_once_dry_run' -Status 'WARN' -Detail 'skipped because python_environment failed'
}

if (-not $SkipCodexCheck) {
    try {
        $codex = Get-LifeOpsCodexCommand
        Add-StartupCheckResult -Name 'codex_cli' -Status 'PASS' -Detail $codex
    } catch {
        Add-StartupCheckResult -Name 'codex_cli' -Status 'WARN' -Detail $_.Exception.Message
    }
}

if ($CheckScheduledTask) {
    try {
        $task = Get-ScheduledTask -TaskName 'LifeOpsCodexOperator' -ErrorAction SilentlyContinue
        if ($task) {
            Add-StartupCheckResult -Name 'startup_registration' -Status 'PASS' -Detail "scheduled task: $($task.State.ToString())"
        } elseif (Test-LifeOpsStartupLauncherInstalled) {
            Add-StartupCheckResult -Name 'startup_registration' -Status 'PASS' -Detail 'Startup folder launcher installed'
        } else {
            Add-StartupCheckResult -Name 'startup_registration' -Status 'WARN' -Detail 'no scheduled task or Startup folder launcher installed'
        }
    } catch {
        if (Test-LifeOpsStartupLauncherInstalled) {
            Add-StartupCheckResult -Name 'startup_registration' -Status 'PASS' -Detail 'Startup folder launcher installed'
        } else {
            Add-StartupCheckResult -Name 'startup_registration' -Status 'WARN' -Detail $_.Exception.Message
        }
    }
}

$summary = [ordered]@{
    generated_at = (Get-Date).ToString('o')
    repo_root = $root
    failures = $failures
    checks = $results
}
$summaryPath = Join-Path $runtimeDir 'startup_check.json'
$summary | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $summaryPath -Encoding UTF8
Write-LifeOpsLog "Test-StartupFlow.ps1 completed with failures=$failures. Summary: $summaryPath"
Write-Host "Summary: $summaryPath"

if ($failures -gt 0) { exit 1 }
exit 0
