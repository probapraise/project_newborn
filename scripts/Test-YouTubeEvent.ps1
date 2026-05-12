. "$PSScriptRoot\LifeOps.Common.ps1"

$python = Initialize-LifeOpsEnvironment
& $python -m lifeops.cli init-db | Out-Null
Write-Host 'Stage 1 확인 완료: DB와 CLI는 준비되었습니다.'
Write-Host 'YouTube 감지/정책 개입 테스트는 Stage 2에서 실제 watcher와 policy engine 연결 후 활성화됩니다.'
