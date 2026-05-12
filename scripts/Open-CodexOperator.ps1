. "$PSScriptRoot\LifeOps.Common.ps1"

$root = Get-LifeOpsRepoRoot
try {
    $python = Initialize-LifeOpsEnvironment
} catch {
    Write-LifeOpsLog "Codex operator launch stopped: $($_.Exception.Message)"
    Show-LifeOpsNotification -Title 'LifeOps Codex' -Message 'Python 3.12+를 찾지 못해 부팅 브리핑을 만들지 못했습니다.'
    exit 1
}

$promptPath = Join-Path $root 'data\exports\boot_prompt.md'
& $python -m lifeops.cli init-db | Out-Null
& $python -m lifeops.cli write-boot-prompt --output $promptPath | Out-Null

try {
    $codex = Get-LifeOpsCodexCommand
} catch {
    Write-LifeOpsLog "Codex CLI not found. Boot briefing window was not opened: $($_.Exception.Message)"
    Show-LifeOpsNotification -Title 'LifeOps Codex' -Message 'Codex CLI를 찾지 못했습니다. PATH 또는 LIFEOPS_CODEX 설정을 확인하세요.'
    exit 1
}

$ps = Get-LifeOpsPowerShell
$srcPath = Join-Path $root 'src'
$escapedRoot = $root.Replace("'", "''")
$escapedPrompt = $promptPath.Replace("'", "''")
$escapedSrc = $srcPath.Replace("'", "''")
$escapedCodex = $codex.Replace("'", "''")
$command = "`$env:LIFEOPS_REPO_ROOT = '$escapedRoot'; `$env:PYTHONPATH = '$escapedSrc'; `$prompt = Get-Content -LiteralPath '$escapedPrompt' -Raw -Encoding UTF8; & '$escapedCodex' --cd '$escapedRoot' --profile lifeops `$prompt"

$wt = Get-Command wt.exe -ErrorAction SilentlyContinue
if ($wt) {
    Start-Process -FilePath $wt.Source -ArgumentList @('new-tab', '--title', 'LifeOps Codex Operator', $ps, '-NoExit', '-Command', $command)
    Write-LifeOpsLog 'Opened Codex operator in Windows Terminal.'
} else {
    Start-Process -FilePath $ps -ArgumentList @('-NoExit', '-Command', $command)
    Write-LifeOpsLog 'Opened Codex operator in PowerShell window.'
}
