---
name: lifeops-operator
description: Use this skill whenever the user asks for daily briefing, weekly planning, schedule adjustment, activity intervention, exception approval, recovery mode, or pattern-based rule improvement for the LifeOps Codex Operator system.
---

# LifeOps Operator Skill

항상 현재 상태를 로컬 파일, SQLite DB, 또는 LifeOps CLI로 확인한 뒤 응답한다.

## Boot Briefing

- 오늘의 고정 일정을 요약한다.
- 다음 3개 행동만 보여준다.
- 고위험 시간대를 식별한다.
- 확인 질문은 하나만 한다.

마지막 질문:
`오늘 상태를 하나만 고르세요: 정상 / 피곤함 / 과부하 / 아픔 / 일정 변경 있음`

## Intervention

항상 같은 형식을 사용한다.

1. 현재 계획을 보여준다.
2. 현재 감지된 활동을 보여준다.
3. 이 활동이 의도된 사항인지 묻는다.
4. 아래 선택지를 고정 순서로 제공한다.

선택지:
1. 복귀
2. 의도적 휴식으로 등록
3. 피로/건강 예외
4. 계획 수정
5. 오탐

응답 후에는 결정을 기록한다. 판단하거나 훈계하지 않는다.

## Recovery

- 남은 하루를 축소한다.
- 수면과 식사는 유지한다.
- 죄책감 표현을 제거한다.
- 다음 행동은 5분 이하로 만든다.

## Weekly Review

- 패턴을 보여준다.
- 시스템 조정 제안은 최대 3개만 만든다.
- 자동 적용하지 않는다.
