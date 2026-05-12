# Current Status and Roadmap

Last updated: 2026-05-12

이 문서는 세션이 바뀌어도 LifeOps Codex Operator의 현재 목표, 완성된 범위, 다음 작업 순서를 빠르게 복구하기 위한 인계 문서다.

프로젝트의 최신 스펙 정의는 `docs/project_spec_v2.md`를 우선한다. 이 문서는 진행 상태와 다음 작업 순서를 추적한다.

## Clean Repo 기준

현재 기준 저장소는 WSL2 내부의 `/home/ljhljh/projects/project_newborn`이다. 이전 Windows-native 작업 폴더 `/home/ljhljh/project_newborn`은 참조용 source-of-truth/archive로만 남긴다.

새 repo 원칙:

- Git history는 새로 쌓는다.
- runtime DB/log/export, self-check 산출물, Windows ACL 백업 폴더는 이관하지 않는다.
- `스펙 시트.txt`는 민감할 수 있는 초기 요구사항 원문이므로 공개 GitHub repo에 올리지 않는다.
- `.gitattributes`로 line ending을 고정하고 BOM/CRLF 노이즈를 제거한다.
- 코어 로직은 WSL2에서 검증하고 Windows 의존 기능은 bridge로 격리한다.

## 핵심 목표

LifeOps Codex Operator는 사용자의 별도 AI 앱이 아니라, Codex CLI/Codex app을 대화 표면으로 사용하는 로컬 생활 운영 시스템이다. 목표는 ADHD+ASD 혼재 성향 사용자가 매번 강한 의지나 긴 자기설명 없이도 평균 이상으로 생활 운영을 이어가도록 돕는 것이다.

시스템은 사용자를 평가하거나 통제하는 권위자가 아니다. 사용자가 사전에 위임한 규칙을 기억하고, 계획과 실제 행동의 차이를 감지하며, 필요한 순간에 복구 가능한 다음 행동을 제시하는 deterministic substrate + Codex Operator 구조다.

## 절대 조건

- 대화 주체는 Codex CLI 또는 Codex app이어야 한다.
- 별도 챗봇 GUI를 만들지 않는다.
- ChatGPT 웹 UI를 자동으로 열지 않는다.
- OpenAI SDK 또는 `api.openai.com` 직접 호출 코드를 만들지 않는다.
- 키 입력, 스크린샷, 브라우저 페이지 본문을 수집하지 않는다.
- 실패 횟수, 벌점, 생산성 점수, 무결점 streak를 표시하지 않는다.
- 사용자가 승인하지 않은 생활 규칙, 차단 규칙, 스케줄 정책 변경을 자동 적용하지 않는다.
- 반복 이탈은 사용자 문제가 아니라 시스템 조정 신호로 본다.

## 현재 단순화된 감시 범위

현재 시스템은 감시 범위를 Chrome과 Steam으로 제한한다.

- Chrome: `chrome.exe`
- Steam: `steam.exe`, `steamwebhelper.exe`
- 모든 게임은 Steam에 등록해서 실행한다고 가정한다.
- Steam이 실행한 foreground 앱은 개별 exe 목록 없이 `steam-launched-app`으로 정규화한다.
- Edge, Firefox, Brave, Epic, Riot, Battle.net, GOG, 개별 게임 exe 카탈로그는 기본 감시 대상이 아니다.
- 감시 범위 밖 프로세스는 창 제목을 저장하지 않고 개입 대상으로 삼지 않는다.

이 범위를 넓히는 변경은 자동 적용하지 말고 시스템 조정 제안으로만 남긴다.

## 오퍼레이터 정체성

오퍼레이터 이름은 `루멘(Lumen)`이다.

루멘은 차분한 계약 기반 실행 코치다. 핵심 역할은 사용자가 사전에 위임한 규칙을 기억하고, 현재 상황을 실행 가능한 다음 행동으로 바꾸는 것이다.

기준 문서:

- `docs/operator_persona.md`
- `AGENTS.md`
- `.agents/skills/lifeops-operator/references/shame_safe_language.md`
- `.agents/skills/lifeops-operator/references/adhd_asd_principles.md`

루멘의 기본 문법은 다음 순서를 따른다.

1. 관찰
2. 충돌 설명
3. 선택지
4. 다음 행동

## 완료된 범위

### Stage 1: 로컬 기반 구축 완료

구현 완료:

- 저장소 기본 구조
- `AGENTS.md`
- `.codex/config.toml`
- `.codex/rules/lifeops.rules`
- LifeOps Codex skill scaffold
- 기본 설정 파일
  - `config/life_rules.yaml`
  - `config/schedule_policy.yaml`
  - `config/blocklist.yaml`
  - `config/intervention_policy.yaml`
  - `config/calendar_policy.yaml`
  - `config/privacy_policy.yaml`
- SQLite DB 스키마
- JSONL 이벤트 로그 디렉터리
- 부팅 브리핑 컨텍스트/프롬프트 생성
- Windows 로그온 자동 시작 설치/삭제 스크립트, 권한 제한 시 Startup 폴더 fallback
- watcher/dispatcher 실행 스크립트
- 기본 CLI
- Stage 1 테스트

주요 파일:

- `src/lifeops/db.py`
- `src/lifeops/boot.py`
- `src/lifeops/cli.py`
- `scripts/Start-LifeOps.ps1`
- `scripts/Install-StartupTask.ps1`
- `scripts/Remove-StartupTask.ps1`
- `tests/test_stage1_bootstrap.py`

### 감시 범위 단순화 완료

구현 완료:

- Chrome/Steam 범위 정책 문서화
- `config/app_scope.yaml`
- `docs/scope_constraints.md`
- `src/lifeops/app_scope.py`
- AGENTS에 감시 범위 반영
- 테스트 추가

핵심 결정:

- 브라우저는 Chrome만 본다.
- 게임은 Steam을 단일 진입점으로 본다.
- 개별 게임 exe 목록은 만들지 않는다.

### Stage 2 일부 완료: Chrome/Steam foreground watcher

구현 완료:

- Windows foreground window 감지
- Chrome/Steam 범위 내 활동만 기록
- 감시 범위 밖 활동은 제목 저장 없이 무시
- Chrome 제목/도메인 힌트 기반 위험 활동 분류 골격
- `config/activity_rules.toml` 기반 Chrome/Steam activity 룰북
- 룰북에 없는 Chrome 활동에 대한 계획 적합 여부 확인 개입
- `plan_aligned` decision과 반복 패턴 기반 learned judgment
- Steam 및 Steam 하위 foreground 앱을 게임 게이트웨이로 분류
- 현재 계획 블록과 충돌 시 `intervention_events`에 pending 이벤트 생성
- 개입 쿨다운 기본 정책
- pending event를 intervention prompt로 렌더링
- Codex intervention 창 실행 브리지
- dispatch 중복 방지용 `dispatching` 상태 전환
- Stage 2 활동/dispatcher 테스트 추가
- watcher/dispatcher 1회 실행 옵션 추가
- startup flow self-check 스크립트 추가
- intervention loop self-check 스크립트 추가
- Codex CLI 경로를 PATH 또는 LIFEOPS_CODEX로 확인

주요 파일:

- `src/lifeops/windows_activity.py`
- `src/lifeops/activity_watcher.py`
- `src/lifeops/browser_activity.py`
- `src/lifeops/rulebook.py`
- `src/lifeops/activity_patterns.py`
- `src/lifeops/policy_engine.py`
- `src/lifeops/event_dispatcher.py`
- `src/lifeops/codex_bridge.py`
- `src/lifeops/models.py`
- `tests/test_stage2_activity.py`
- `tests/test_stage2_dispatcher.py`

현재 watcher는 감지와 기록을 하고, dispatcher는 pending 이벤트를 루멘 intervention prompt로 만들어 Codex 창으로 전달한다. 사용자의 응답은 고정 선택지 코드로 기록되며, 휴식/피로/건강/과부하/계획 수정은 예외 기록과 연결된다. startup flow self-check 스크립트도 추가되어 긴 실행 없이 DB 초기화, boot prompt 생성, watcher 1회, dispatcher dry-run 1회를 확인할 수 있다. intervention loop self-check는 테스트용 Steam 이벤트를 만들고 prompt 생성과 decision 기록까지 닫으며, 테스트용 일정 블록은 실행 후 자동으로 취소한다.

사용자 PowerShell 검증 결과(2026-05-12): startup flow self-check에서 repo_root, powershell, python_environment, init_db, boot_context, boot_prompt, watcher_once, dispatcher_once_dry_run, codex_cli가 PASS였다. 예약 작업 등록은 권한 문제로 Startup 폴더 launcher fallback을 사용했고, `startup_registration`도 PASS였다. `Test-InterventionLoop.ps1` 실행 결과 `status=pass`, `dispatch_status=dispatched`, `decision=return_now`, `final_event_status=decided`로 확인되었다. 이후 `Test-InterventionLoop.ps1 -CleanupOnly`는 남은 self-check 일정 1개를 정리했고, `Enter-RecoveryMode.ps1 -Reason fatigue -DryRun`은 protected/deferred 항목 0개와 fallback next action을 정상 출력했다. `Test-RecoveryDecisionFlow.ps1`도 sandbox에서 `status=pass`로 확인되었고, protected block 보존, optional block 취소, high task 보존, low task defer가 모두 통과했다.

남은 Stage 2 핵심은 실제 Windows 재로그인/재부팅 후 `Start-LifeOps.ps1`가 자동 실행되어 `data/runtime/startup.log`와 watcher/dispatcher pid가 새로 찍히는지 확인하는 것이다.

### 오퍼레이터 persona 완료

구현 완료:

- `docs/operator_persona.md`
- 오퍼레이터 이름 `루멘(Lumen)` 정의
- 기본 성격, 말투, 금지 표현, 상황별 모드 정의
- AGENTS에서 persona 문서를 먼저 읽도록 연결

## Legacy 커밋 흐름

아래 목록은 이전 Windows-native 작업 폴더의 의미 단위 커밋 기록이다. 새 clean repo는 이 히스토리를 그대로 가져오지 않고 기능 단위로 다시 쌓는다.

1. `a7a6aba Implement LifeOps Stage 1 scaffold`
2. `8aabb36 Constrain monitoring scope to Chrome and Steam`
3. `40df891 Implement Chrome and Steam activity watcher`
4. `5d39086 Define LifeOps operator persona`
5. `4742b1c Document current status and roadmap`
6. `2952b8b Implement intervention dispatcher`
7. `a25a3ba Improve intervention decision logging`
8. `25b86ba Add startup flow self-check`
9. `1091244 Document Windows PowerShell startup commands`
10. `281b790 Support configured Codex CLI path`
11. `8e2c3cc Fallback to Startup launcher for autostart`
12. `5dea975 Fix scheduled task run level`
13. `d6b175a Add intervention loop self-check`
14. `2f40e06 Document Stage 2 self-check results`
15. `07cf633 Implement recovery mode`
16. `e523cd5 Fix recovery mode preview timestamp`
17. `f91bfc7 Clean up self-check artifacts`
18. `28f9480 Connect decisions to recovery mode`
19. `bc3b053 Add recovery decision self-check`
20. `cf4ff58 Fix recovery decision self-check task expectations`

이 문서 이후의 새 clean repo 커밋은 `git log --oneline`으로 확인한다.

## 현재 알려진 제한과 주의점

- WSL 환경에는 `python3`가 있으며 `python` 명령은 기본 등록되어 있지 않을 수 있다.
- `pytest`가 없으면 `PYTHONPATH=src python3 -m unittest discover -s tests`로 baseline을 확인한다.
- `.agents`와 `.codex` 디렉터리는 Codex 환경에서 read-only mount 제약이 걸릴 수 있다. 루트 `AGENTS.md`와 `docs/operator_persona.md`를 우선 기준으로 둔다.
- `스펙 시트.txt`, 로컬 DB, 이벤트 로그, runtime 파일은 민감하거나 로컬 상태 파일이므로 Git에 올리지 않는다.

## 다음 작업 목록

### 1. Stage 2-D: 실제 부팅/로그온 동작 점검

목표:

Windows 로그인 후 Start-LifeOps가 watcher, dispatcher, Codex boot briefing을 안정적으로 실행하는지 확인한다.

Clean repo에서는 이 목표를 WSL2 core / Windows bridge 기준으로 다시 닫는다.

구현 시작:

- `python3 -m lifeops.server --host 127.0.0.1 --port 8765`
- `GET /health`
- `POST /events/activity`
- `GET /interventions/pending`
- `POST /interventions/{event_id}/decision`
- `POST /recovery/enter`
- `windows_bridge/Run-ActivityBridge.ps1`
- `windows_bridge/Notify-Intervention.ps1`
- `windows_bridge/Register-StartupTask.ps1`

해야 할 일:

- `Install-StartupTask.ps1` 실제 등록 테스트, 권한 거부 시 Startup 폴더 fallback 확인
- task scheduler 동작 확인
- watcher/dispatcher pid 파일 확인
- `Test-StartupFlow.ps1 -CheckScheduledTask` self-check 결과 확인
- boot prompt 생성 확인
- Codex CLI 실행 경로 확인
- 로그 파일 회전 또는 크기 제한 검토

완료 기준:

- 사용자가 직접 실행하지 않아도 로그인 후 LifeOps가 시작된다.
- 실패 시 원인을 `data/runtime/startup.log`에서 확인할 수 있다.

### 2. Stage 3-A: recovery mode 실사용화

목표:

반복 이탈, 피로, 과부하 상황에서 남은 하루 계획을 자동으로 축소하고 다음 3-5분 행동만 남긴다.

구현 완료:

- `src/lifeops/recovery.py`
- `scripts/Enter-RecoveryMode.ps1`
- `scripts/Record-InterventionDecision.ps1`
- `scripts/Test-RecoveryDecisionFlow.ps1`
- `python -m lifeops.cli enter-recovery-mode --reason ...`
- `python -m lifeops.cli record-decision --enter-recovery-mode ...`
- `python -m lifeops.recovery_decision_self_check`
- recovery session 기록
- 남은 비필수 schedule block을 `cancelled`로 전환
- 남은 비필수 task를 `deferred_recovery`로 전환
- 수면, 식사, 복약, 위생, 고정 일정, work block 보호
- recovery prompt 생성
- dry-run preview 지원
- 자가점검용 `source=self_check` 일정 블록을 recovery plan에서 제외
- intervention decision에서 `--enter-recovery-mode`로 recovery mode 연결
- recovery decision flow를 실제 DB와 분리된 sandbox에서 검증하는 self-check
- daily summary에 recovery usage와 exception category 집계 반영
- daily summary를 루멘이 읽을 수 있는 운영 요약 형식으로 개선
- 사용자 PowerShell에서 self-check cleanup, recovery dry-run, recovery decision self-check 확인

남음:

- 사용자 PowerShell에서 daily summary 생성 확인
- weekly pattern analysis 준비

완료 기준:

- 사용자가 회복 모드를 선택하면 남은 하루가 작게 재구성된다.
- 죄책감/벌칙 없이 다음 행동이 생성된다.

### 3. Stage 3-B: daily summary와 weekly review

목표:

일일 요약과 주간 패턴 분석을 통해 시스템 조정 제안을 최대 3개만 만든다.

해야 할 일:

- activity/intervention/decision 로그 요약 1차 구현
- 피로 예외, 복귀 시간, 반복 마찰 지점 집계
- `codex exec`용 weekly pattern prompt 정리
- activity rule proposal을 weekly review에 연결
- rule proposal 승인 후 `config/activity_rules.toml`에 반영하는 workflow
- 승인 전 자동 적용 금지

완료 기준:

- 매일 짧은 운영 요약이 생성된다.
- 주간 리뷰에서 시스템 조정 제안이 최대 3개 생성된다.

### 4. Stage 4: Chrome extension과 Native Messaging

목표:

Chrome title 기반 추정을 넘어, Chrome 도메인만 안정적으로 보고하는 확장을 붙인다.

해야 할 일:

- Chrome extension scaffold
- Native Messaging host
- 도메인-only reporting
- page body 수집 금지 검증
- redirect/friction page

완료 기준:

- Chrome의 현재 도메인을 페이지 본문 없이 안전하게 기록한다.
- 위험 도메인에서 마찰 또는 redirect가 가능하다.

### 5. Stage 4 후반: calendar 연동

목표:

캘린더 API 또는 ICS export를 통해 일정 블록을 안정적으로 가져오거나 내보낸다.

해야 할 일:

- 우선 ICS export/import 설계
- Google/Microsoft calendar API는 별도 인증이 필요하므로 후순위
- schedule_blocks 동기화 규칙
- 수동 입력과 캘린더 충돌 처리

완료 기준:

- 고정 일정이 DB schedule_blocks에 반영된다.
- 캘린더 연동은 LLM API와 무관하게 동작한다.

### 6. Stage 5: MCP/tool 고도화

목표:

Codex가 LifeOps 상태를 더 안정적으로 읽고 기록할 수 있는 tool interface를 제공한다.

해야 할 일:

- `lifeops-mcp` 서버 구체화
- get_current_block, get_pending_events, record_decision tool화
- rule proposal 승인 workflow
- 상태 변경 audit log

완료 기준:

- Codex가 DB를 직접 SQL로 만지는 대신 안정된 도구를 통해 상태를 읽고 쓴다.

## 다음 세션의 첫 권장 작업

가장 먼저 할 일은 Stage 2-D의 마지막 실제 로그온 확인이다.

시작 순서:

1. Windows에서 로그아웃 후 다시 로그인하거나 재부팅한다
2. 로그인 후 `data/runtime/startup.log`의 최신 timestamp를 확인한다
3. `data/runtime/watcher.pid`와 `data/runtime/dispatcher.pid`가 생겼는지 확인한다
4. `scripts/Test-StartupFlow.ps1 -CheckScheduledTask`를 다시 실행한다
5. Codex boot briefing 창이 열렸는지 확인한다
6. 문제가 없으면 `scripts/Enter-RecoveryMode.ps1 -Reason fatigue -DryRun`으로 recovery preview를 확인한다
7. recovery 적용 경로는 먼저 `scripts/Test-RecoveryDecisionFlow.ps1`로 격리 검증한다
8. 실제 event 적용 검증은 pending event id를 확인한 뒤 `scripts/Record-InterventionDecision.ps1 -EventId <id> -Choice fatigue -EnterRecoveryMode` 경로로 확인한다

이 작업이 끝나면 Stage 2의 핵심 루프와 Stage 3-A 회복 모드를 실제 Windows 환경에서 신뢰할 수 있게 된다.
