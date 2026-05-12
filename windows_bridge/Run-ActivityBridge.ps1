param(
    [string]$CoreUrl = 'http://127.0.0.1:8765',
    [int]$IntervalSeconds = 5,
    [switch]$Once,
    [switch]$SampleActivity,
    [string]$AutoChoice = ''
)

Set-StrictMode -Version Latest
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Add-Type @'
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class LifeOpsWin32 {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);
}
'@

function Get-ForegroundActivity {
    if ($SampleActivity) {
        return @{
            timestamp = [DateTimeOffset]::UtcNow.ToString('o')
            process_name = 'chrome.exe'
            window_title = 'YouTube - Chrome'
            domain = 'youtube.com'
            classification = 'chrome'
        }
    }

    $hwnd = [LifeOpsWin32]::GetForegroundWindow()
    if ($hwnd -eq [IntPtr]::Zero) { return $null }

    [uint32]$foregroundProcessId = 0
    [void][LifeOpsWin32]::GetWindowThreadProcessId($hwnd, [ref]$foregroundProcessId)
    if ($foregroundProcessId -eq 0) { return $null }

    $process = Get-Process -Id $foregroundProcessId -ErrorAction SilentlyContinue
    if (-not $process) { return $null }

    $name = ($process.ProcessName + '.exe').ToLowerInvariant()
    $classification = 'ignored'
    if ($name -eq 'chrome.exe') {
        $classification = 'chrome'
    } elseif ($name -eq 'steam.exe' -or $name -eq 'steamwebhelper.exe') {
        $classification = 'steam'
    } else {
        return $null
    }

    $buffer = New-Object System.Text.StringBuilder 512
    [void][LifeOpsWin32]::GetWindowText($hwnd, $buffer, $buffer.Capacity)
    $title = ($buffer.ToString() -replace '\s+', ' ').Trim()

    return @{
        timestamp = [DateTimeOffset]::UtcNow.ToString('o')
        process_name = $name
        window_title = $title
        classification = $classification
    }
}

function Send-Activity {
    param([hashtable]$Activity)

    $json = $Activity | ConvertTo-Json -Depth 4
    return Invoke-RestMethod -Method Post -Uri "$CoreUrl/events/activity" -ContentType 'application/json; charset=utf-8' -Body $json
}

try {
    Invoke-RestMethod -Method Get -Uri "$CoreUrl/health" | Out-Null
} catch {
    Write-Host "WSL core에 연결할 수 없습니다: $CoreUrl"
    exit 1
}

$lastKey = ''
do {
    $activity = Get-ForegroundActivity
    if ($activity) {
        $key = "$($activity.process_name)|$($activity.window_title)|$($activity.classification)"
        if ($key -ne $lastKey) {
            $response = Send-Activity -Activity $activity
            if ($response.intervention -and $response.intervention.status -eq 'pending') {
                $notifyArgs = @{
                    CoreUrl = $CoreUrl
                    EventId = [int]$response.intervention.id
                }
                if ($AutoChoice) {
                    $notifyArgs.AutoChoice = $AutoChoice
                }
                & (Join-Path $PSScriptRoot 'Notify-Intervention.ps1') @notifyArgs
            }
            $lastKey = $key
        }
    }

    if (-not $Once) {
        Start-Sleep -Seconds $IntervalSeconds
    }
} while (-not $Once)
