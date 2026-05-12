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

## 로그온 등록

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\windows_bridge\Register-StartupTask.ps1
```
