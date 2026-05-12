. "$PSScriptRoot\LifeOps.Common.ps1"

$root = Get-LifeOpsRepoRoot
$codex = Get-Command codex -ErrorAction SilentlyContinue
if (-not $codex) {
    Write-LifeOpsLog 'Codex CLI not found. Weekly analysis skipped.'
    Show-LifeOpsNotification -Title 'LifeOps Codex' -Message 'Codex CLI를 찾지 못해 주간 분석을 실행하지 못했습니다.'
    exit 1
}

$date = Get-Date -Format 'yyyy-MM-dd'
$output = Join-Path $root "data\proposals\weekly_$date.md"
$prompt = Get-Content -LiteralPath (Join-Path $root 'prompts\pattern_analysis_prompt.md') -Raw -Encoding UTF8
& $codex.Source exec --cd $root --profile lifeops -o $output $prompt
Write-LifeOpsLog "Weekly analysis written to $output."
