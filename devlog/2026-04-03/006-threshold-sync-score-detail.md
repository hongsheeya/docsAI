# Threshold 동기화 및 점수 계산식 실제 값 표시

- **ID**: 006
- **날짜**: 2026-04-03
- **유형**: 버그 수정

## 작업 요약
프론트엔드에 하드코딩된 threshold 43%를 실제 백엔드 값 52%로 수정하고, 점수 계산식(`getRiskScoreFormula()`)을 백엔드 응답 데이터 기반 동적 표시로 변경했다. 추가로 분석 결과 카드에 Motion Guard 적용 여부, Short-clip 상태, Raw/최종 확률 비교 등 중간값을 시각적 배지로 표시.

## 변경 파일 목록

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - `effectiveThreshold` fallback: 0.43 → 0.52
  - `getRiskScoreFormula()`: 하드코딩 43% 삭제, `risk_score_guide.threshold`·`short_clip.effective_threshold`·`motion_guard.applied` 기반 동적 생성
  - RF-Pose 모델 타입별 formula 분기 추가
- `src/app/page.dashboard/view.pug`
  - 점수 계산식 카드에 Motion Guard / Short-clip / Raw↔최종 확률 배지 3종 추가
