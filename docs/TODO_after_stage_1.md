# TODO After Stage 1

## Current Scope Constraint

- 감시 대상은 Chrome과 Steam으로 제한한다.
- Chrome: `chrome.exe`만 감시한다.
- Steam: `steam.exe`, `steamwebhelper.exe`만 감시한다.
- 모든 게임은 Steam에 등록해서 실행한다고 가정한다.
- 다른 브라우저, 다른 게임 런처, 개별 게임 exe 목록은 Stage 2 기본 범위에서 제외한다.

## Stage 2

완료:
- Chrome/Steam 전용 foreground window watcher 구현
- Chrome 제목/도메인 힌트 기반 활동 분류 골격
- Steam 실행/활성 창/Steam 하위 프로세스 기반 게임 게이트웨이 분류
- 기본 policy engine 구현
- pending intervention event 생성
- Codex intervention prompt 렌더링
- intervention dispatcher가 pending event를 Codex 창으로 전달
- decision logging 기본 CLI
- 선택지 코드 기반 decision logging UX
- 휴식/피로/건강/과부하/계획 수정 선택을 exception 기록과 연결
- watcher/dispatcher 1회 실행 옵션
- startup flow self-check 스크립트
- intervention loop self-check 스크립트
- 사용자 PowerShell startup self-check PASS 확인
- 사용자 PowerShell intervention loop self-check PASS 확인

남음:
- 반복 개입 UX 다듬기
- 실제 Chrome/Steam 사용 중 개입 루프 관찰
- 재로그인/재부팅 후 Startup launcher 실제 실행 확인

## Stage 3

진행 중/완료:
- recovery mode 실제 계획 축소
- recovery session 기록
- recovery prompt 생성
- 비필수 schedule block/task defer
- intervention decision에서 recovery mode로 이어지는 명시 옵션
- recovery decision flow 격리 self-check
- daily summary에 recovery usage와 exception category 반영
- daily summary를 루멘이 읽을 수 있는 운영 요약 형식으로 개선

남음:
- 사용자 PowerShell에서 daily summary 생성 확인
- weekly pattern analysis using `codex exec`

## Stage 4

- Chrome extension
- Native Messaging host
- Chrome domain-only reporting
- redirect/friction page
- ICS export 또는 calendar API sync

## Stage 5

- lifeops-mcp 서버
- Codex tool interface
- rule proposal approval workflow 고도화
