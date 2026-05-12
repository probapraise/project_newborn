# Project Spec v2

Last updated: 2026-05-12

이 문서는 LifeOps Codex Operator가 무엇을 만들려는 프로젝트인지 다시 고정하기 위한 새 스펙이다. 기존 `스펙 시트.txt`의 철학과 금지 조건은 유지하되, 현재 clean repo와 WSL2 core / Windows bridge 전환 상태에 맞게 범위와 순서를 재정의한다.

## 1. 한 줄 정의

LifeOps Codex Operator는 사용자의 생활 계획과 실제 컴퓨터 사용 사이의 어긋남을 로컬에서 감지하고, Codex CLI/app을 통해 짧고 예측 가능한 선택지를 제시하며, 결정/예외/회복 흐름을 기록하는 로컬 생활 운영 보조 시스템이다.

이 시스템은 별도 챗봇 앱이 아니다. OpenAI API 직접 호출 앱도 아니다. 핵심은 deterministic local substrate가 상태를 만들고, Codex가 사용자의 대화 표면과 판단 보조자 역할을 맡는 구조다.

## 2. 사용자가 만들고 싶은 것

사용자는 매일 강한 의지나 긴 자기설명을 반복하지 않고도 생활 운영이 평균 이상으로 굴러가길 원한다. 특히 변동 근무, 피로 상태, 주간 휴식일, 우선순위, Chrome/Steam 사용 같은 현실 신호를 시스템이 기억하고, 필요한 순간에 다음 행동을 작게 만들어주길 원한다.

따라서 이 프로젝트의 실제 목표는 다음이다.

- 오늘의 계획, 고정 일정, 다음 행동을 Codex가 빠르게 읽을 수 있게 만든다.
- Chrome/Steam 활동이 현재 계획과 어긋날 때 shame-safe intervention을 띄운다.
- 사용자는 복귀, 의도적 휴식, 피로/건강/과부하 예외, 계획 수정, 오탐 중 하나를 고른다.
- 선택은 SQLite DB와 JSONL 로그에 기록된다.
- 피로/과부하/계획 수정은 남은 하루를 줄이는 recovery mode로 연결할 수 있다.
- 매일/매주 요약은 사용자를 평가하지 않고 시스템 조정 후보만 만든다.
- 반복되는 어긋남은 사용자 문제가 아니라 시스템 조정 신호로 본다.

## 3. 만들지 않는 것

아래 항목은 이 프로젝트의 목표가 아니다.

- ChatGPT 웹 자동 실행
- 별도 챗봇 GUI
- OpenAI SDK 또는 `api.openai.com` 직접 호출
- 사용자를 점수화하는 생산성 앱
- 키 입력 기록기
- 스크린샷 감시기
- 브라우저 페이지 본문 수집기
- 모든 앱 사용을 추적하는 활동 감시기
- 모든 게임 실행 파일을 카탈로그화하는 런처 감시기
- 우회 불가능한 강제 차단 시스템
- 사용자를 교정하거나 훈계하는 도덕 평가 시스템

## 4. 핵심 철학

기존 스펙의 핵심 철학은 유지한다.

- 최적 계획보다 생각 비용이 낮은 운영 시스템이 우선이다.
- 예외는 실패가 아니라 정상 제어 흐름이다.
- 수면, 식사, 복약, 위생, 주간 완전 휴식일은 보호 대상이다.
- ADHD 실행기능 보조와 ASD 예측 가능성을 우선한다.
- hyperfocus 전환은 `저장 -> 전환 -> 다음 행동` 순서로 다룬다.
- burnout 방지를 위해 계획 크기를 줄일 수 있어야 한다.
- 반복 이탈은 차단 강도를 즉시 올릴 이유가 아니라 시스템 조정 신호다.
- 규칙 변경은 사용자 승인 전에는 적용하지 않는다.

## 5. 언어와 UX 원칙

사용자-facing 문구는 한국어를 기본으로 한다. 코드와 파일명은 영어를 쓴다.

금지 표현:

- 실패
- 위반
- 벌점
- 의지 부족
- 게으름
- 불이행
- 왜 그랬나요?
- 당신은 지금 회피하고 있습니다

권장 표현:

- 현재 계획과 감지된 활동이 어긋났습니다.
- 지금 어떻게 처리할까요?
- 예외로 기록하고 계획을 조정합니다.
- 오늘 계획을 현재 상태에 맞게 줄입니다.
- 시스템 조정 제안으로 남깁니다.

개입 선택지 기본 순서:

1. 지금 복귀
2. 의도적 휴식으로 등록
3. 피로/건강/과부하 예외
4. 계획 자체를 수정
5. 오탐으로 표시

## 6. 현재 아키텍처

현재 기준 아키텍처는 Windows-native 단일 구조가 아니라 WSL2 core / Windows bridge 구조다.

```text
[Windows Activity Bridge]
Chrome/Steam foreground 감지
        |
        | localhost HTTP
        v
[WSL2 LifeOps Core]
DB 기록, 정책 판단, pending intervention 생성
        |
        | response / pending decision payload
        v
[Windows Bridge UI]
고정 선택지 표시
        |
        | decision POST
        v
[WSL2 LifeOps Core]
decision, exception, recovery 기록
        |
        v
[Codex CLI/app]
부팅 브리핑, 개입 설명, 회복 코칭, 주간 리뷰
```

## 7. 컴포넌트 책임

### 7.1 WSL2 LifeOps Core

WSL core는 시스템의 판단과 상태 변경을 맡는다.

- SQLite schema/init/connect
- activity event 저장
- schedule block 조회
- Chrome/Steam activity 평가
- pending intervention 생성
- intervention decision 기록
- exception 기록
- recovery mode 적용
- boot briefing context/prompt 생성
- daily summary 생성
- weekly pattern context 생성
- localhost API 제공
- 테스트와 검증 기준 유지

주요 파일:

- `src/lifeops/db.py`
- `src/lifeops/activity_watcher.py`
- `src/lifeops/policy_engine.py`
- `src/lifeops/server.py`
- `src/lifeops/bridge_protocol.py`
- `src/lifeops/decision_logging.py`
- `src/lifeops/recovery.py`
- `src/lifeops/daily_summary.py`
- `src/lifeops/pattern_miner.py`

### 7.2 Windows Bridge

Windows bridge는 얇고 교체 가능해야 한다. 정책 판단을 중복 구현하지 않는다.

- foreground window 감지
- Chrome/Steam process normalization
- WSL core `/health` 확인
- WSL core `/events/activity` 전송
- pending intervention이 있으면 고정 선택지 표시
- decision payload를 WSL core로 POST
- Windows 로그온 자동 시작 등록

금지:

- Chrome/Steam 외 foreground 창 제목 저장
- 키 입력 수집
- 스크린샷 수집
- 브라우저 페이지 본문 수집
- 정책 판단 중복 구현

주요 파일:

- `windows_bridge/Run-ActivityBridge.ps1`
- `windows_bridge/Notify-Intervention.ps1`
- `windows_bridge/Test-BridgeFlow.ps1`
- `windows_bridge/Register-StartupTask.ps1`

### 7.3 Codex Operator

Codex는 사용자가 실제로 대화하는 표면이다.

- 부팅 브리핑을 보여준다.
- pending intervention 상황을 짧게 설명한다.
- 선택지를 해석한다.
- 회복 모드 prompt를 사용자에게 설명한다.
- daily/weekly summary를 바탕으로 시스템 조정 제안을 만든다.

Codex는 사용자의 인격이나 의지를 평가하지 않는다.

## 8. 데이터 정책

저장 가능:

- timestamp
- process name
- Chrome/Steam window title
- Chrome domain
- current schedule block id
- activity classification
- intervention reason/risk/status
- user decision code
- exception category/duration
- recovery session summary
- daily/weekly deterministic summary

저장 금지:

- 키 입력
- 스크린샷
- 브라우저 페이지 본문
- 비밀번호/시크릿/개인 메시지 본문
- Chrome/Steam 외 앱의 창 제목
- 전체 프로세스 사용 히스토리
- 생산성 점수, 벌점, streak

## 9. 감시 범위

MVP 감시 범위는 의도적으로 작다.

- Chrome: `chrome.exe`
- Steam: `steam.exe`, `steamwebhelper.exe`
- Steam이 실행한 foreground 앱은 필요 시 `steam-launched-app`으로 정규화한다.

제외:

- Edge
- Firefox
- Brave
- Opera
- Epic Games Launcher
- Riot Client
- Battle.net
- GOG Galaxy
- 개별 게임 exe 목록

감시 범위 확대는 코드 변경으로 바로 적용하지 않는다. 먼저 시스템 조정 제안으로 남기고 사용자가 승인한 뒤 반영한다.

## 9.1 Activity rulebook

Chrome/Steam 분류는 코드에 직접 문자열을 누적하지 않는다. 수정 가능한 룰북을 둔다.

현재 룰북:

- `config/activity_rules.toml`

룰북 원칙:

- rule category는 `aligned`, `distracting`, `unknown`으로 해석한다.
- Chrome은 domain과 foreground window title fragment만 사용한다.
- page body, screenshot, keystroke는 룰 조건으로 쓰지 않는다.
- 업무/자료 확인 사이트는 `aligned` rule로 둔다.
- 영상/SNS/커뮤니티 사이트는 `distracting` rule로 둔다.
- Steam은 기본적으로 보호 블록 중 distracting으로 본다.

룰북에 없는 Chrome 활동 처리:

```text
Chrome foreground
-> 룰북에 domain/title match 없음
-> 현재 계획 블록이 work/study/research 등 보호/집중 블록
-> pending clarification intervention 생성
-> "현재 계획은 X인데, 이 활동은 계획에 맞나요?"라고 확인
```

사용자 결정은 다음 패턴 학습 신호가 된다.

- `plan_aligned`: 현재 계획에 맞는 사용으로 학습 후보
- `return_now`: 계획과 어긋나는 사용으로 학습 후보
- `intentional_rest`: 현재 계획과 다르지만 예외/휴식으로 처리
- `false_positive`: 감지/분류 조정 후보

반복 패턴 장치:

- 같은 domain/title 패턴에 대해 일관된 결정이 2회 이상 쌓이면 learned judgment로 사용한다.
- 반복적으로 `plan_aligned`가 선택된 패턴은 같은 상황에서 더 이상 매번 묻지 않고 log-only로 처리할 수 있다.
- 반복적으로 `return_now`가 선택된 패턴은 계획과 어긋나는 활동으로 판단한다.
- `generate-activity-rule-proposals` CLI는 반복 결정에서 `rule_proposals` 후보를 만든다.
- 승인 전에는 룰북 파일을 자동 수정하지 않는다.

## 10. API 계약

기본 bind:

- host: `127.0.0.1`
- port: `8765`

필수 endpoint:

- `GET /health`
- `POST /events/activity`
- `GET /interventions/pending?limit=1`
- `POST /interventions/{event_id}/decision`
- `POST /recovery/enter`

activity payload:

```json
{
  "timestamp": "2026-05-12T15:00:00+09:00",
  "process_name": "chrome.exe",
  "window_title": "YouTube - Chrome",
  "domain": "youtube.com",
  "classification": "chrome"
}
```

decision payload:

```json
{
  "choice": "return_now",
  "duration_minutes": null,
  "reason": null,
  "followup_action": null,
  "enter_recovery_mode": false
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

## 11. 현재 구현 상태

완료:

- clean WSL repo 생성
- GitHub `probapraise/project_newborn`에 clean history push
- repo hygiene: `.gitattributes`, `.gitignore`
- AGENTS/persona/config/prompts/docs 이관
- SQLite schema
- boot briefing context/prompt
- Chrome/Steam scope policy
- activity snapshot 평가
- intervention event 생성
- decision logging
- exception 기록
- recovery mode
- daily summary
- weekly pattern context groundwork
- WSL core API
- Windows bridge scaffold
- Windows bridge sample flow
- 테스트 37개 통과

검증된 흐름:

```text
WSL core 실행
-> /health 200 OK
-> Windows bridge sample activity POST
-> pending intervention 생성
-> return_now decision POST
-> event status decided
```

현재 확인된 한계:

- 실제 foreground bridge `-Once`는 실행 순간 Windows Terminal이 foreground이면 Chrome을 감지하지 않는다.
- 실제 Chrome/Steam 감지는 long-running bridge 또는 foreground 전환 대기 옵션이 필요하다.
- Windows bridge UI는 아직 콘솔 선택지 방식이다.
- WSL core 자동 시작과 Windows bridge 자동 시작은 아직 완전히 재설계되지 않았다.
- weekly analysis는 context 생성 기반만 있고 Codex exec proposal 생성/승인 workflow는 미완성이다.
- Chrome extension, friction/redirect, calendar sync, MCP server는 아직 후순위 scaffold다.

## 12. 기존 스펙과의 대조

| 항목 | 기존 스펙 | v2 재정의 |
| --- | --- | --- |
| 목표 | ADHD+ASD 생활 운영 보조 | 동일. 단, MVP는 Chrome/Steam 어긋남 감지와 회복 루프에 집중 |
| 실행 환경 | Windows 11 중심 | WSL2 core + Windows bridge |
| Codex 역할 | 대화 표면, 브리핑/개입/회고 | 동일. API 직접 호출 없이 Codex CLI/app 사용 |
| 감시 범위 | Chrome/Edge 가능성, 브라우저 확장 후속 | MVP는 Chrome/Steam만. Edge/기타 런처 제외 |
| 자동 실행 | Windows Scheduled Task 중심 | WSL core 자동 시작 + Windows bridge 자동 시작으로 분리 필요 |
| 활동 감지 | Windows watcher 직접 실행 | bridge가 감지하고 WSL core가 판단 |
| 정책 판단 | Python watcher/policy | WSL core에 집중. bridge에는 판단 금지 |
| 데이터 저장 | SQLite/JSONL | 동일. runtime/generated는 Git 제외 |
| Intervention UX | Codex 창 우선 | 현재는 bridge console 선택지 + 추후 Codex/Toast 연계 |
| Recovery mode | Stage 3 목표 | 구현됨. decision에서 연결 가능 |
| Daily summary | Stage 3 목표 | 구현됨 |
| Weekly analysis | Codex exec 목표 | groundwork만 있음. 다음 단계 |
| MCP | Stage 5 | 아직 scaffold |
| Chrome extension | Stage 4 | 아직 보류 |
| Calendar sync | Stage 4 후반 | 아직 보류 |

## 13. 새 개발 단계

### Phase 0: Clean foundation 완료

완료 기준:

- clean repo가 WSL 내부에 있다.
- runtime/generated/민감 파일이 Git에서 제외된다.
- 테스트가 통과한다.
- GitHub main에 push된다.

상태: 완료

### Phase 1: WSL core API MVP 완료

완료 기준:

- `/health` 동작
- sample activity POST 동작
- pending intervention 생성
- decision POST 동작
- recovery enter endpoint 동작
- tests 통과

상태: 대부분 완료

남은 확인:

- API idempotency
- error response 정리
- runtime log/queue

### Phase 2: Windows bridge 실사용 검증

목표:

실제 Chrome/Steam foreground 전환을 bridge가 안정적으로 WSL core에 전달한다.

해야 할 일:

- `Run-ActivityBridge.ps1`에 foreground wait/test 옵션 추가
- Chrome foreground 실제 기록 확인
- Steam foreground 실제 기록 확인
- Chrome/Steam 외 foreground 무시 확인
- bridge 실패 로그 작성
- long-running bridge 중복 이벤트 억제 검증
- 콘솔 선택지 UX를 임시 MVP로 유지할지, toast/small window로 바꿀지 결정

완료 기준:

- Chrome YouTube foreground가 WSL DB에 기록된다.
- 현재 보호 블록과 충돌하면 pending intervention이 생긴다.
- 선택지에서 `return_now`를 고르면 event가 `decided`가 된다.
- 감시 범위 밖 창 제목은 저장되지 않는다.

### Phase 3: 자동 시작 재설계

목표:

컴퓨터 로그인 후 사용자가 직접 감시 장치를 실행하지 않아도 core와 bridge가 켜진다.

해야 할 일:

- WSL core 자동 시작 방식 결정
- Windows bridge Scheduled Task 등록
- core가 꺼져 있을 때 bridge가 실패를 기록하는 방식 추가
- startup health check script 작성
- pid/log 관리

완료 기준:

- 로그인 후 WSL core가 뜬다.
- Windows bridge가 뜬다.
- `data/runtime` 또는 Windows-side log에서 상태를 확인할 수 있다.

### Phase 4: Codex intervention 연결 정리

목표:

pending intervention이 생겼을 때 최종 대화 표면을 Codex로 자연스럽게 연결한다.

선택지:

- bridge console 선택지를 MVP로 유지
- Windows toast로 Codex/선택지 열기
- Codex CLI intervention prompt 창 열기
- MCP/tool 기반으로 Codex가 decision 기록

완료 기준:

- 사용자가 별도 앱을 쓰지 않고 Codex 또는 bridge 선택지에서 결정을 기록할 수 있다.
- 사용자-facing 문구가 루멘 persona를 따른다.

### Phase 5: Daily/weekly review 실사용화

목표:

누적 로그를 사용자 평가가 아니라 시스템 조정 제안으로 바꾼다.

해야 할 일:

- weekly context CLI 추가
- `Run-WeeklyAnalysis.ps1`를 WSL 기준으로 재작성
- Codex exec prompt 정리
- activity rule proposal 생성 CLI를 weekly review에 연결
- rule proposal 승인/룰북 반영 workflow 정리
- proposal은 최대 3개만 생성
- 승인 전 자동 적용 금지

완료 기준:

- 매일 summary가 생성된다.
- 주간 리뷰에서 시스템 조정 제안이 최대 3개 생성된다.
- boot briefing에서 pending proposal을 보여준다.

### Phase 6: 후순위 확장

후순위 항목:

- Chrome extension domain-only reporting
- Native Messaging
- friction/redirect page
- ICS export/import
- calendar sync
- MCP server
- richer Codex tools

이 항목들은 Phase 2-5가 안정화된 뒤 진행한다.

## 14. 다음에 바로 할 일

가장 가까운 작업은 룰북 기반 unknown Chrome clarification 루프를 실사용 검증하는 것이다.

구체 순서:

1. 현재 시간대에 work/study 보호 블록을 만든다.
2. `Run-ActivityBridge.ps1 -WaitSeconds 10`을 실행한다.
3. 실행 후 룰북에 없는 Chrome 사이트로 포커스를 옮긴다.
4. bridge가 현재 계획/감지 활동/사유를 보여주며 “현재 계획에 맞나요?”라고 묻는지 확인한다.
5. `plan_aligned` 또는 `return_now` 결정을 기록한다.
6. 같은 패턴이 반복될 때 learned judgment와 `generate-activity-rule-proposals`가 작동하는지 확인한다.

이 작업이 끝나면 프로젝트의 첫 실사용 루프가 닫힌다.

```text
Chrome foreground
-> Windows bridge 감지
-> WSL core 기록/판단
-> pending intervention
-> 계획 적합 여부 선택지
-> decision 기록
-> 반복 패턴 학습/제안
```

## 15. 성공 기준

이 프로젝트의 성공 기준은 사용자를 더 강하게 막는 것이 아니다. 성공 기준은 사용자가 생활 운영을 다시 시작하는 비용이 낮아지는 것이다.

측정할 수 있는 운영 신호:

- 어긋남 감지 후 결정까지의 시간
- 오탐 수
- 피로/과부하 예외 사용
- recovery mode 사용
- pending intervention 미처리 수
- 반복 마찰 지점
- 시스템 조정 제안 승인/보류 이력

측정하지 않는 것:

- 실패 횟수
- 순종률
- 생산성 점수
- streak
- 벌점
