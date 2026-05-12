Set-StrictMode -Version Latest

function Get-LifeOpsRepoRoot {
    return (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
}

function Get-LifeOpsPowerShell {
    $pwsh = Get-Command pwsh -ErrorAction SilentlyContinue
    if ($pwsh) { return $pwsh.Source }
    $powershell = Get-Command powershell -ErrorAction SilentlyContinue
    if ($powershell) { return $powershell.Source }
    throw 'PowerShell executable not found.'
}

function Get-LifeOpsCodexCommand {
    if ($env:LIFEOPS_CODEX -and (Test-Path -LiteralPath $env:LIFEOPS_CODEX)) {
        return (Resolve-Path -LiteralPath $env:LIFEOPS_CODEX).Path
    }

    $cmd = Get-Command codex -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @()
    if ($env:APPDATA) {
        $candidates += (Join-Path $env:APPDATA 'npm\codex.cmd')
        $candidates += (Join-Path $env:APPDATA 'npm\codex.ps1')
    }
    if ($env:LOCALAPPDATA) {
        $candidates += (Join-Path $env:LOCALAPPDATA 'OpenAI\Codex\bin\codex.exe')
        $candidates += (Join-Path $env:LOCALAPPDATA 'Programs\Codex\codex.exe')
    }

    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw 'Codex CLI not found. Add codex to PATH or set LIFEOPS_CODEX to codex.cmd/exe.'
}

function Assert-LifeOpsPythonVersion {
    param(
        [Parameter(Mandatory=$true)][string]$PythonPath
    )

    $global:LASTEXITCODE = 0
    $version = & $PythonPath -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}'); raise SystemExit(0 if sys.version_info >= (3, 12) else 1)" 2>$null
    $exitCode = $global:LASTEXITCODE
    if ($exitCode -ne 0) {
        if (-not $version) { $version = 'unknown' }
        throw "Python 3.12+ is required; found $version at $PythonPath."
    }
    return $version
}

function Get-LifeOpsPythonCommand {
    if ($env:LIFEOPS_PYTHON -and (Test-Path -LiteralPath $env:LIFEOPS_PYTHON)) {
        return $env:LIFEOPS_PYTHON
    }

    foreach ($name in @('python', 'python3', 'py')) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }

    $commonRoots = @()
    if ($env:LOCALAPPDATA) {
        $commonRoots += (Join-Path $env:LOCALAPPDATA 'Programs\Python')
    }
    if ($env:ProgramFiles) {
        $commonRoots += $env:ProgramFiles
    }
    if (${env:ProgramFiles(x86)}) {
        $commonRoots += ${env:ProgramFiles(x86)}
    }
    $commonRoots = $commonRoots | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($base in $commonRoots) {
        $candidate = Get-ChildItem -LiteralPath $base -Filter python.exe -Recurse -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending |
            Select-Object -First 1
        if ($candidate) { return $candidate.FullName }
    }

    throw 'Python 3.12+ is required but no Python executable was found. Set LIFEOPS_PYTHON to python.exe if needed.'
}

function Write-LifeOpsLog {
    param(
        [Parameter(Mandatory=$true)][string]$Message
    )
    $root = Get-LifeOpsRepoRoot
    $logDir = Join-Path $root 'data\runtime'
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $timestamp = Get-Date -Format o
    Add-Content -LiteralPath (Join-Path $logDir 'startup.log') -Value "$timestamp $Message" -Encoding UTF8
}

function Initialize-LifeOpsEnvironment {
    $root = Get-LifeOpsRepoRoot
    $venv = Join-Path $root '.venv'
    $venvPython = Join-Path $venv 'Scripts\python.exe'

    if (-not (Test-Path -LiteralPath $venvPython)) {
        $python = Get-LifeOpsPythonCommand
        $version = Assert-LifeOpsPythonVersion -PythonPath $python
        Write-LifeOpsLog "Creating Python virtual environment with $python (version $version)."
        & $python -m venv $venv
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $venvPython)) {
            throw 'Failed to create Python virtual environment.'
        }
    }

    $version = Assert-LifeOpsPythonVersion -PythonPath $venvPython
    Write-LifeOpsLog "Using LifeOps Python environment $venvPython (version $version)."
    $env:LIFEOPS_REPO_ROOT = $root
    $env:PYTHONPATH = Join-Path $root 'src'
    return $venvPython
}

function Test-LifeOpsProcessAlive {
    param(
        [Parameter(Mandatory=$true)][string]$PidFile
    )
    if (-not (Test-Path -LiteralPath $PidFile)) { return $false }
    $text = Get-Content -LiteralPath $PidFile -Raw -ErrorAction SilentlyContinue
    $pidValue = 0
    if (-not [int]::TryParse($text.Trim(), [ref]$pidValue)) { return $false }
    $process = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    return [bool]$process
}

function Start-LifeOpsManagedProcess {
    param(
        [Parameter(Mandatory=$true)][string]$Name,
        [Parameter(Mandatory=$true)][string]$ScriptPath
    )
    $root = Get-LifeOpsRepoRoot
    $runtime = Join-Path $root 'data\runtime'
    New-Item -ItemType Directory -Path $runtime -Force | Out-Null
    $pidFile = Join-Path $runtime "$Name.pid"

    if (Test-LifeOpsProcessAlive -PidFile $pidFile) {
        Write-LifeOpsLog "$Name already running."
        return
    }

    $ps = Get-LifeOpsPowerShell
    $args = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $ScriptPath)
    $process = Start-Process -FilePath $ps -ArgumentList $args -WindowStyle Hidden -PassThru
    Set-Content -LiteralPath $pidFile -Value $process.Id -Encoding ASCII
    Write-LifeOpsLog "$Name started with pid $($process.Id)."
}

function Get-LifeOpsStartupLauncherPath {
    $startupDir = [Environment]::GetFolderPath('Startup')
    if (-not $startupDir) {
        throw 'Current user Startup folder was not found.'
    }
    return (Join-Path $startupDir 'LifeOpsCodexOperator.cmd')
}

function Install-LifeOpsStartupLauncher {
    param(
        [Parameter(Mandatory=$true)][string]$PowerShellPath,
        [Parameter(Mandatory=$true)][string]$StartScript
    )

    $launcherPath = Get-LifeOpsStartupLauncherPath
    $launcherDir = Split-Path -Parent $launcherPath
    New-Item -ItemType Directory -Path $launcherDir -Force | Out-Null
    $launchCommand = 'start "" /min "{0}" -NoProfile -ExecutionPolicy Bypass -File "{1}"' -f $PowerShellPath, $StartScript
    $content = @(
        '@echo off',
        $launchCommand
    )
    Set-Content -LiteralPath $launcherPath -Value $content -Encoding ASCII
    Write-LifeOpsLog "Installed Startup folder launcher: $launcherPath"
    return $launcherPath
}

function Remove-LifeOpsStartupLauncher {
    $launcherPath = Get-LifeOpsStartupLauncherPath
    if (Test-Path -LiteralPath $launcherPath) {
        Remove-Item -LiteralPath $launcherPath -Force
        Write-LifeOpsLog "Removed Startup folder launcher: $launcherPath"
        return $true
    }
    return $false
}

function Test-LifeOpsStartupLauncherInstalled {
    try {
        $launcherPath = Get-LifeOpsStartupLauncherPath
        return (Test-Path -LiteralPath $launcherPath)
    } catch {
        return $false
    }
}

function Show-LifeOpsNotification {
    param(
        [Parameter(Mandatory=$true)][string]$Title,
        [Parameter(Mandatory=$true)][string]$Message
    )
    try {
        Add-Type -AssemblyName System.Windows.Forms -ErrorAction Stop
        Add-Type -AssemblyName System.Drawing -ErrorAction Stop
        $notify = New-Object System.Windows.Forms.NotifyIcon
        $notify.Icon = [System.Drawing.SystemIcons]::Information
        $notify.BalloonTipTitle = $Title
        $notify.BalloonTipText = $Message
        $notify.Visible = $true
        $notify.ShowBalloonTip(5000)
        Start-Sleep -Seconds 6
        $notify.Dispose()
    } catch {
        Write-LifeOpsLog "$Title - $Message"
    }
}
