param(
    [string]$CoreUrl = 'http://127.0.0.1:8765',
    [string]$Choice = 'return_now'
)

Set-StrictMode -Version Latest
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Invoke-RestMethod -Method Get -Uri "$CoreUrl/health" | Out-Null

& (Join-Path $PSScriptRoot 'Run-ActivityBridge.ps1') `
    -CoreUrl $CoreUrl `
    -Once `
    -SampleActivity `
    -AutoChoice $Choice

$pending = Invoke-RestMethod -Method Get -Uri "$CoreUrl/interventions/pending?limit=1"
Write-Host "pending_after_test=$($pending.items.Count)"
