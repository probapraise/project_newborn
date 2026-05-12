param(
    [string]$CoreUrl = 'http://127.0.0.1:8765',
    [int]$EventId = 0
)

Set-StrictMode -Version Latest

$choices = @(
    @{ Number = '1'; Choice = 'return_now'; Label = '지금 복귀' },
    @{ Number = '2'; Choice = 'intentional_rest'; Label = '의도적 휴식으로 등록' },
    @{ Number = '3'; Choice = 'fatigue'; Label = '피로 예외' },
    @{ Number = '4'; Choice = 'adjust_plan'; Label = '계획 자체를 수정' },
    @{ Number = '5'; Choice = 'false_positive'; Label = '오탐으로 표시' }
)

if ($EventId -le 0) {
    $pending = Invoke-RestMethod -Method Get -Uri "$CoreUrl/interventions/pending?limit=1"
    if (-not $pending.items -or $pending.items.Count -eq 0) {
        Write-Host 'pending intervention 없음'
        exit 0
    }
    $EventId = [int]$pending.items[0].id
}

Write-Host ''
Write-Host "LifeOps intervention #$EventId"
Write-Host '현재 계획과 감지된 활동이 어긋났습니다. 지금 어떻게 처리할까요?'
foreach ($item in $choices) {
    Write-Host "$($item.Number). $($item.Label)"
}

$answer = Read-Host '선택'
$selected = $choices | Where-Object { $_.Number -eq $answer -or $_.Choice -eq $answer } | Select-Object -First 1
if (-not $selected) {
    Write-Host '선택을 기록하지 않았습니다.'
    exit 2
}

$body = @{
    choice = $selected.Choice
    reason = 'Windows bridge selection'
}

if ($selected.Choice -eq 'intentional_rest') {
    $body.duration_minutes = 15
}
if ($selected.Choice -eq 'fatigue') {
    $body.duration_minutes = 30
    $body.enter_recovery_mode = $true
}

$json = $body | ConvertTo-Json -Depth 4
Invoke-RestMethod -Method Post -Uri "$CoreUrl/interventions/$EventId/decision" -ContentType 'application/json; charset=utf-8' -Body $json | Out-Null
Write-Host '결정을 기록했습니다.'
