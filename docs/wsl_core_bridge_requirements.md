# WSL2 Core / Windows Bridge Requirements

Last updated: 2026-05-12

이 문서는 LifeOps Codex Operator를 Windows-native 개발 흐름에서 WSL2 중심 개발 흐름으로 옮기기 위한 요구사항이다. 목표는 기존 프로젝트를 폐기하지 않고, 코어 로직은 WSL2/Linux에 두며, Windows 제어가 필요한 부분만 얇은 브리지로 격리하는 것이다.

## 결정 사항

- 개발 주체: WSL2 안의 Codex CLI
- 보조 편집기: VS Code Remote WSL
- Windows Codex 앱: 설계 논의/검토용 보조 인터페이스. 현재는 메인 개발 주체로 쓰지 않는다.
- 코어 위치: WSL2 내부 파일시스템
  - 예: `~/projects/project_newborn`
  - Windows 경로 `/mnt/c/...`는 메인 작업 위치로 쓰지 않는다.
- 실행 방식:
  - WSL2 core가 DB, 정책 판단, prompt 생성, recovery/daily summary를 담당한다.
  - Windows bridge가 Chrome/Steam 감시, Windows 알림, 시작프로그램/작업 스케줄러, 앱/파일 열기 같은 OS 접점을 담당한다.

## 유지해야 할 프로젝트 원칙

`AGENTS.md`, `docs/operator_persona.md`, `config/life_rules.yaml`, `config/schedule_policy.yaml`, `config/intervention_policy.yaml`을 우선한다.

- 사용자에게 실패, 게으름, 불이행, 의지 부족, 위반 프레임을 쓰지 않는다.
- 예외는 정상적인 제어 흐름으로 처리한다.
- 개입 선택지는 3-5개로 유지하고, 기본 순서를 보존한다.
- hyperfocus 전환은 `저장 -> 전환 -> 다음 행동` 순서를 사용한다.
- 수면, 식사, 복약, 위생, 주간 완전 휴식일은 하드 제약으로 보호한다.
- 사용자가 승인하지 않은 생활 규칙, 차단 규칙, 스케줄 정책 변경을 자동 적용하지 않는다.
- OpenAI SDK를 직접 쓰지 않는다.
- `api.openai.com`에 직접 요청하는 코드를 만들지 않는다.
- ChatGPT 웹 UI를 자동으로 열지 않는다.
- 별도 챗봇 GUI를 만들지 않는다.
- 키 입력, 스크린샷, 브라우저 페이지 본문을 수집하지 않는다.
- 실패 횟수, 벌점, streak, 생산성 점수를 표시하지 않는다.

## 감시 범위

현재 MVP 감시 범위는 Chrome과 Steam만이다.

- Chrome: `chrome.exe`
- Steam: `steam.exe`, `steamwebhelper.exe`
- Steam이 실행한 foreground 앱은 개별 exe 카탈로그 없이 `steam-launched-app`으로 정규화한다.
- Edge, Firefox, Brave, Epic, Riot, Battle.net, GOG, 개별 게임 exe 카탈로그는 기본 감시 대상이 아니다.
- 감시 범위 확대는 자동 적용하지 말고 시스템 조정 제안으로만 남긴다.

## 목표 아키텍처

```text
[Windows activity bridge]
Chrome/Steam foreground 감지
        |
        | localhost HTTP 또는 명시적 CLI 호출
        v
[WSL2 LifeOps core]
DB 기록, 정책 판단, pending intervention 생성
        |
        | response / pending decision payload
        v
[Windows bridge UI]
Toast 또는 작은 선택지 창
        |
        | decision POST
        v
[WSL2 LifeOps core]
decision/exceptions/recovery 기록
```

## WSL2 Core 책임

기존 `src/lifeops` 패키지를 유지하고, 첫 단계에서 대규모 rename은 피한다.

WSL2 core에 남길 책임:

- SQLite DB schema/init/connect
- JSONL event append
- schedule policy
- intervention policy
- activity snapshot 평가
- pending intervention 생성
- intervention decision 기록
- exception 기록
- recovery mode
- boot briefing context/prompt 생성
- daily summary
- weekly/pattern analysis
- CLI
- tests
- localhost API service

Windows-specific import가 Linux import 경로를 깨지 않도록 한다. 예를 들어 `ctypes.windll`, foreground window API, PowerShell launcher는 Linux에서 import되지 않게 분리한다.

## Windows Bridge 책임

Windows bridge는 얇고 교체 가능해야 한다. 비즈니스 판단을 넣지 않는다.

Windows bridge에 둘 책임:

- foreground window 감지
- Chrome/Steam process normalization
- Steam 하위 foreground app을 `steam-launched-app`으로 정규화
- WSL2 core로 activity event 전송
- WSL2 core가 반환한 intervention payload를 Windows 알림/선택지 UI로 표시
- 사용자 선택을 WSL2 core로 전송
- Windows 로그온 자동 시작 등록
- 필요 시 파일/앱 열기

금지:

- 키 입력 수집
- 스크린샷 수집
- 브라우저 페이지 본문 수집
- Chrome/Steam 외 프로세스의 창 제목 저장
- 정책 판단을 bridge에 중복 구현

## 통신 방식

MVP는 localhost HTTP를 우선한다.

권장 endpoint:

- `GET /health`
- `POST /events/activity`
- `GET /interventions/pending?limit=1`
- `POST /interventions/{event_id}/decision`
- `POST /recovery/enter`

요구사항:

- 기본 bind는 `127.0.0.1`만 사용한다.
- 기본 port는 `8765`로 시작한다.
- Windows bridge는 WSL2 core가 꺼져 있을 때 실패를 조용히 삼키지 말고 `data/runtime` 또는 Windows 쪽 queue/log에 남긴다.
- core API는 동일 이벤트 반복 전송에 대비해 가능한 한 idempotent하게 설계한다.
- API payload에는 민감한 원문을 넣지 않는다.

## Activity Event Payload

Windows bridge가 WSL2 core에 보내는 최소 payload:

```json
{
  "timestamp": "2026-05-12T15:00:00+09:00",
  "process_name": "chrome.exe",
  "window_title": "YouTube - Chrome",
  "domain": "youtube.com",
  "classification": "risky_browser"
}
```

규칙:

- Chrome/Steam 범위 밖 활동은 기본적으로 전송하지 않는다.
- 범위 밖 활동을 전송해야 할 필요가 생기면 `classification: "ignored"`로 제한하고, 창 제목은 보내지 않는다.
- Chrome은 도메인과 창 제목만 허용한다. 페이지 본문은 금지한다.

## Intervention Decision Payload

사용자 선택지는 기존 정책과 호환되어야 한다.

```json
{
  "choice": "return_now",
  "duration_minutes": null,
  "reason": null,
  "followup_action": null
}
```

허용 choice:

- `return_now`
- `intentional_rest`
- `fatigue`
- `health`
- `overload`
- `adjust_plan`
- `false_positive`

Windows UI 표시 순서:

1. 지금 복귀
2. 의도적 휴식으로 등록
3. 피로/건강/과부하 예외
4. 계획 자체를 수정
5. 오탐으로 표시

## 추천 파일 배치

첫 단계에서는 기존 구조를 최대한 유지한다.

```text
src/lifeops/
  core modules remain here
  server.py                    # WSL localhost API
  bridge_protocol.py           # request/response schema helpers
  windows_activity.py          # Windows-only, import guarded
  activity_watcher.py          # refactor toward provider/process_snapshot split

windows_bridge/
  Run-ActivityBridge.ps1
  Notify-Intervention.ps1
  Register-StartupTask.ps1
  README.md

scripts/
  dev.sh
  run-core.sh
  test.sh
```

중요: Python package rename은 1차 작업에서 하지 않는다. `lifeops` import 경로와 기존 테스트가 깨지지 않는 상태에서 분리한다.

## 작업 단계

### 0. WSL 환경 점검

- WSL2 내부 파일시스템에 프로젝트를 둔다.
- Python 3.12 이상을 사용한다.
- Codex sandbox 안정성을 위해 `bubblewrap`을 설치한다.
- 현재 테스트를 먼저 실행해 baseline을 잡는다.

### 1. 플랫폼 의존성 분리

- Linux에서 `import lifeops`가 성공해야 한다.
- Windows-only API는 호출 시점까지 import되지 않도록 한다.
- `activity_watcher.process_snapshot()`처럼 플랫폼 독립 로직은 core로 유지한다.
- foreground 감지 provider만 Windows bridge로 분리한다.

### 2. WSL core API 추가

- stdlib 우선으로 구현한다. 필요성이 명확해지기 전에는 FastAPI 등 새 dependency를 추가하지 않는다.
- `python -m lifeops.server --host 127.0.0.1 --port 8765` 형태로 실행 가능하게 한다.
- `/events/activity`는 기존 `ActivitySnapshot`, `evaluate_activity`, DB insert 흐름을 재사용한다.
- pending intervention이 생기면 bridge가 표시할 수 있는 짧은 payload를 반환한다.

### 3. Windows bridge MVP

- PowerShell script로 시작한다.
- foreground 감지와 HTTP POST만 담당한다.
- 사용자에게 개입이 필요할 때는 고정 선택지 UI를 띄우고 decision endpoint로 보낸다.
- Windows bridge가 정책 판단을 직접 하지 않게 한다.

### 4. 실행 스크립트 정리

- WSL:
  - `scripts/dev.sh`
  - `scripts/run-core.sh`
  - `scripts/test.sh`
- Windows:
  - `windows_bridge/Run-ActivityBridge.ps1`
  - `windows_bridge/Register-StartupTask.ps1`

### 5. 문서 갱신

- `README.md`
- `docs/current_status_and_roadmap.md`
- 필요하면 `docs/scope_constraints.md`

문서에는 Windows-native Codex 앱이 아니라 WSL2 Codex CLI를 개발 주체로 삼는다고 명시한다.

## Acceptance Criteria

WSL2에서:

- `python -m pytest` 통과
- `python -m lifeops.cli init-db` 성공
- `python -m lifeops.cli write-boot-prompt` 또는 현재 CLI 하위 명령 동등 기능 성공
- `python -m lifeops.server --once` 또는 health check 가능한 방식으로 core API 검증
- sample activity event POST 시 DB에 activity event가 기록됨
- 정책상 개입이 필요한 sample event에서 pending intervention 생성됨
- decision POST 시 intervention decision과 exception/recovery 연결이 기존 로직과 호환됨

Windows에서:

- bridge가 Chrome/Steam만 감지함
- Chrome/Steam 외 foreground는 제목을 저장하지 않음
- bridge가 WSL core `/health` 확인 가능
- bridge가 sample event를 WSL core에 전송 가능
- pending intervention을 사용자 선택지로 표시 가능
- 선택 결과가 WSL DB에 기록됨

## Non-goals

- 별도 챗봇 GUI 만들기
- OpenAI API 직접 호출 기능 추가
- Chrome extension 만들기
- 키 입력/스크린샷/브라우저 본문 수집
- 감시 대상을 Chrome/Steam 밖으로 확장
- 대규모 패키지 rename
- 처음부터 전체 재작성

## 운영 판단

이 전환은 Windows 자동화를 포기하는 것이 아니다. Windows 권한/샌드박스 문제를 코어 개발 경로에서 제거하고, Windows 의존 부분을 작고 명시적인 bridge로 제한하는 구조 조정이다.

첫 성공 기준은 완벽한 자동화가 아니라 다음 흐름을 닫는 것이다.

```text
Windows에서 Chrome/Steam 감지
-> WSL core에 event 기록
-> policy 판단
-> pending intervention 생성
-> Windows에서 고정 선택지 표시
-> decision 기록
```
