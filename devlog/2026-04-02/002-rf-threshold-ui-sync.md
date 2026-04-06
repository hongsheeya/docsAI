# RF Threshold UI 동기화 및 Motion Guard 보정

- **ID**: 002
- **날짜**: 2026-04-02
- **유형**: 버그 수정 / 설정 변경

## 작업 요약
RF 파이프라인 재학습 결과(threshold 0.25)를 사이트 전체 UI 문구에 반영하고, motion guard 억제값이 새 threshold와 겹치는 문제를 수정했다.

## 변경 파일 목록

### Pipeline 페이지 (UI 텍스트 수정)
- `src/app/page.pipeline/view.pug` — RF 낙상 임계값 표시: 60% → 25%

### Dashboard 페이지 (UI 텍스트 수정)
- `src/app/page.dashboard/view.ts` — `getRiskScoreFormula()` RF 공식 텍스트: threshold(50%) → threshold(25%)

### 백엔드 모델 (로직 수정)
- `src/model/struct/video_analysis.py`
  - 주석 업데이트: "threshold is 60%" → "Threshold is now 0.25 (optimized retrain)"
  - AR-only motion guard 억제값: `min(score, 0.25)` → `min(score, 0.20)` — threshold=0.25와 동일해서 억제된 결과도 "주의"로 표시되던 문제 수정. 이제 0.20으로 설정하여 올바르게 "안정"으로 분류됨.
