# LifeOps Codex Operator

LifeOps Codex Operator는 Codex CLI/Codex app을 생활 운영 보조자로 사용하는 로컬 시스템이다. 별도 챗봇 GUI나 OpenAI API 직접 호출 없이, 로컬 DB와 스크립트가 Codex에게 필요한 상태만 전달한다.

## 현재 개발 기준

이 저장소는 WSL2 안의 clean repo를 기준으로 다시 쌓는다.

- 코어 로직은 WSL2/Linux에서 import/test 가능해야 한다.
- Windows 제어가 필요한 foreground 감시, 알림, 로그온 자동 시작은 얇은 bridge로 격리한다.
- 기존 Windows-native 실험 흔적, runtime DB/log, ACL 백업, generated prompt는 Git에 올리지 않는다.
- 새 기능은 의미 단위 커밋으로 쌓고, 공개 GitHub repo `probapraise/project_newborn`에 push한다.

## Stage 1 범위

- 저장소 기본 구조
- Codex Operator용 `AGENTS.md`
- 기본 생활 규칙/스케줄/개입/프라이버시 설정
- SQLite DB 스키마 초기화
- 부팅 브리핑 컨텍스트 생성
- Windows 로그온 자동 시작 작업 설치/삭제 스크립트
- Codex CLI 실행 스크립트
- Stage 2용 watcher/dispatcher 자리표시자

브라우저 확장, 실제 브라우저 도메인 감지, 캘린더 API 연동은 Stage 1 이후 TODO로 남겨져 있다.

## Stage 2 진행

현재 watcher는 Windows foreground 창에서 Chrome/Steam만 감시한다.

- Chrome: `chrome.exe`의 창 제목과 제목에서 확인 가능한 도메인 힌트만 기록한다.
- Steam: `steam.exe`, `steamwebhelper.exe`, 그리고 Steam이 실행한 foreground 앱을 게임 활동의 단일 진입점으로 본다.
- 감시 범위 밖 프로세스는 제목을 저장하지 않고 개입 대상으로 삼지 않는다. Steam 하위 앱은 개별 exe 목록 없이 `steam-launched-app`으로만 정규화한다.
- 현재 계획 블록과 어긋나는 Steam 활동 또는 주의가 필요한 Chrome 활동은 `intervention_events`에 pending 상태로 기록한다.
- dispatcher는 pending event를 루멘 intervention prompt로 렌더링하고 Codex intervention 창으로 전달한다.
- decision logging은 선택지 코드 기반으로 기록하며, 휴식/피로/건강/과부하/계획 수정은 예외 기록과 연결된다.

Codex intervention prompt dispatch, decision logging 기본 UX, startup flow self-check 스크립트가 구현되었다. 다음 Stage 2 작업은 사용자의 일반 PowerShell에서 self-check를 실행하고 예약 작업을 실제 로그온 환경에서 확인하는 것이다.

현재 상태와 다음 작업 목록은 [current_status_and_roadmap.md](docs/current_status_and_roadmap.md)를 기준으로 한다.

## 수동 1회 시작

PowerShell에서 저장소 루트로 이동한 뒤 실행한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-LifeOps.ps1
```

## Startup flow 점검

장시간 프로세스를 띄우지 않고 부팅 경로를 점검한다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-StartupFlow.ps1 -CheckScheduledTask
```

이 스크립트는 DB 초기화, boot context/prompt 생성, watcher 1회 실행, dispatcher dry-run 1회 실행, Codex CLI/예약 작업 확인 결과를 `data/runtime/startup_check.json`에 남긴다.

Intervention loop 전체를 안전하게 확인하려면 아래 명령을 실행한다. 테스트용 Steam 활동 이벤트를 만들고, prompt를 생성한 뒤 `return_now` 결정으로 닫는다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-InterventionLoop.ps1
```

예외 생성 경로까지 확인하려면 1분짜리 의도적 휴식 예외로 닫을 수 있다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-InterventionLoop.ps1 -Choice intentional_rest -DurationMinutes 1
```

자가점검은 테스트용 일정 블록을 실행 후 자동으로 취소한다. 이전 버전에서 남은 자가점검 일정이 있으면 아래 명령으로 정리한다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-InterventionLoop.ps1 -CleanupOnly
```

## Recovery mode

남은 하루를 최소안으로 줄이고, 비필수 블록/작업을 미루며, recovery prompt를 생성한다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Enter-RecoveryMode.ps1 -Reason fatigue
```

먼저 결과만 보고 싶으면 실제 DB 상태를 바꾸지 않는 dry-run을 쓴다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Enter-RecoveryMode.ps1 -Reason overload -DryRun
```

개입 결정에서 바로 회복 모드까지 이어야 할 때는 아래처럼 기록한다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Record-InterventionDecision.ps1 -EventId 1 -Choice fatigue -DurationMinutes 30 -EnterRecoveryMode
```

실제 일정 DB를 건드리지 않고 이 연결 흐름을 확인하려면 격리된 self-check를 실행한다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Test-RecoveryDecisionFlow.ps1
```

`codex_cli` 경고가 뜨면 Codex CLI 경로를 환경변수로 고정할 수 있다.

```powershell
$env:LIFEOPS_CODEX = "$env:LOCALAPPDATA\OpenAI\Codex\bin\codex.exe"
[Environment]::SetEnvironmentVariable("LIFEOPS_CODEX", $env:LIFEOPS_CODEX, "User")
```

npm 전역 설치를 쓴 환경이면 `$env:APPDATA\npm\codex.cmd`를 대신 지정한다.

## Daily summary

오늘의 운영 요약을 `data/daily/YYYY-MM-DD.md`로 생성한다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Run-DailySummary.ps1
```

특정 날짜를 다시 만들 때는 로컬 날짜를 지정한다.

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\scripts\Run-DailySummary.ps1 -Date 2026-05-12
```

## 자동 시작 설치

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Install-StartupTask.ps1
```

설치 후 Windows 로그인 시 `scripts/Start-LifeOps.ps1`이 실행된다. 예약 작업 등록이 권한 때문에 실패하면 사용자 Startup 폴더 런처로 자동 fallback한다.

## 자동 시작 제거

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Remove-StartupTask.ps1
```

## 주요 CLI

```powershell
$env:PYTHONPATH = ".\src"
python -m lifeops.cli init-db
python -m lifeops.cli export-boot-briefing-context
python -m lifeops.cli write-boot-prompt
python -m lifeops.cli get-today-plan
python -m lifeops.cli get-current-block
```

## Python 경로

Stage 1 런처는 `.venv`가 없으면 Python 3.12+로 가상환경을 만든다. `python`, `python3`, `py` 순서로 찾고, 특수한 설치 경로를 쓰는 경우 아래처럼 지정할 수 있다.

```powershell
$env:LIFEOPS_PYTHON = "C:\Path\To\python.exe"
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-LifeOps.ps1
```
