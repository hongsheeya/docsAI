# 5가지 이슈 일괄 수정

- **ID**: 003
- **날짜**: 2026-04-27
- **유형**: 버그 수정, 기능 추가

## 작업 요약
실시간 로그 "초기 서기 고정" 버그 수정, 발표자료에 HITL·핵심기술 슬라이드 추가,
view.ts 중복 메서드 제거, 매뉴얼 페이지 발표자료 링크 추가, 사이드바 sticky 수정 등 5가지 이슈를 일괄 처리.

## 변경 파일 목록

### 백엔드 (버그 수정)
- `src/model/struct/video_analysis.py`
  - `_posture_available = False` 일 때 `posture_label = 'stand'` 기본값 대신 `''` 반환 (FN-stand-fix)
  - 두 군데 (upload 분석 함수, realtime 분석 함수) 모두 적용
  - 모델이 실제 예측한 'stand'와 초기화 기본값 'stand'를 구분 가능하게 됨

### 발표자료 Angular App (기능 추가)
- `src/app/page.presentation/view.ts`
  - 슬라이드 15 (핵심 기술 스택): XG-Fall, XG-Posture, Motion Gate, Temporal Smoothing, YOLO v8 Pose, 37-feature Engineering 등
  - 슬라이드 16 (HITL 재학습): 피드백 수집 단계, 재학습 트리거, 데이터 누적 전략
  - 중복 `truncate` 메서드 제거 (빌드 오류 원인)
  - 손상된 `accentClass` 메서드 시그니처 복구

- `src/app/page.presentation/view.pug`
  - `twocol` 타입에서 `{label, desc}` 객체 아이템 지원 (plain string 하위호환 유지)

### 매뉴얼 페이지 (UX 개선)
- `src/app/page.manual/view.pug`
  - 헤더 nav에 "발표자료" 링크 버튼 추가 (`/presentation`, violet 테마)
  - `div.flex.h-full.overflow-hidden` → `div.flex.h-full` 로 변경 (overflow-hidden 제거)
  - 사이드바 내부 `sticky` 래퍼 제거 → 사이드바 컬럼 자체에 `overflow-y-auto` 부여
  - sticky 조상에 overflow-hidden이 있으면 동작 안 되는 CSS 제약 해소
