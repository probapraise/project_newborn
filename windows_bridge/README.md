# Windows Bridge

Windows bridge는 비즈니스 판단을 하지 않는다. Chrome/Steam foreground 활동을 최소 payload로 WSL core에 보내고, core가 pending intervention을 반환하면 고정 선택지를 표시한다.

기본 전제:

- WSL core는 `http://127.0.0.1:8765`에서 실행 중이어야 한다.
- bridge는 Chrome/Steam 외 foreground 제목을 전송하지 않는다.
- 정책 판단, 예외 기록, recovery 연결은 WSL core가 맡는다.

## 수동 실행

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\windows_bridge\Run-ActivityBridge.ps1 -Once
```

현재 foreground 앱과 무관하게 core 연결/전송/결정 기록 경로를 점검하려면 sample flow를 사용한다. 단, WSL DB에 현재 시간대의 보호 블록이 있어야 pending intervention이 생성된다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\windows_bridge\Test-BridgeFlow.ps1 -Choice return_now
```

실제 foreground 감지를 확인할 때는 대기 시간을 준 뒤 Chrome 또는 Steam 창으로 포커스를 옮긴다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\windows_bridge\Run-ActivityBridge.ps1 -WaitSeconds 10 -AutoChoice return_now
```

이 명령은 최대 10초 동안 Chrome/Steam foreground를 기다리고, 감지되면 한 번만 core로 전송한다.
`-AutoChoice return_now`는 반드시 같은 줄에 붙인다. 다음 줄에 따로 입력하면 PowerShell은 별도 명령으로 처리한다.

pending intervention이 생기면 bridge는 다음 정보를 표시한다.

- 현재 계획
- 감지된 활동
- 개입 사유
- 현재 계획에 맞음 / 복귀 / 휴식 / 예외 / 계획 수정 / 오탐 선택지

Chrome 활동 분류는 `config/activity_rules.toml` 룰북에서 수정한다. 룰북에 없는 Chrome 활동이 보호 블록 중 감지되면 bridge는 “이 활동은 현재 계획에 맞나요?”라고 확인한다.

## 로그온 등록

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\windows_bridge\Register-StartupTask.ps1
```
