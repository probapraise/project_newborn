# Scope Constraints

현재 프로젝트는 실사용 가능성을 우선하기 위해 감시 대상을 최소화한다.

## 감시 대상

1. Chrome
   - 프로세스: `chrome.exe`
   - 수집: 시간, 창 제목, 도메인
   - 금지: 페이지 본문, 키 입력, 스크린샷

2. Steam
   - 프로세스: `steam.exe`, `steamwebhelper.exe`
   - 의미: 모든 게임 활동의 단일 진입점
   - 금지: 개별 게임 exe 카탈로그 유지, 다른 런처 감시

## 기본 제외 대상

- Edge, Firefox, Brave, Opera
- Epic Games Launcher
- Riot Client
- Battle.net
- GOG Galaxy
- 개별 게임 실행 파일 목록

## 설계 효과

- Stage 2 watcher는 모든 프로세스를 의미 있게 분류하려 하지 않는다.
- Chrome/Steam 외 프로세스는 기본적으로 무시한다.
- 반복적인 오탐이 생기면 감시 범위를 넓히기보다 시스템 조정 제안으로 남긴다.
