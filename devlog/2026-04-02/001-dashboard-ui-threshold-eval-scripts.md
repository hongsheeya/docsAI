# 대시보드 UI 재구성, RF threshold 조정, 평가 스크립트 생성

- **ID**: 001
- **날짜**: 2026-04-02
- **유형**: 기능 추가 / UI 개선 / 스크립트 생성

## 작업 요약
FN-20260402-0001~0011 전체 11개 작업 일괄 수행. 대시보드 결과 UI 단순화(빠른요약 삭제, 카드 재배치, 2열 그리드, 헤더 축소), 엔진 라벨 통일, 점수 계산식 표시, RF threshold 50% 조정, RF/XGBoost 정밀 평가 스크립트 생성.

## 변경 파일 목록

### 대시보드 UI (FN-0001~0003, 0005~0008)
- `src/app/page.dashboard/view.pug` — 전면 재작성
  - 빠른 요약 카드 삭제
  - 사용된 분석 엔진 카드를 판단 근거 아래로 이동
  - 판단 근거 항목 `md:grid-cols-2` 적용
  - nav 헤더 py-4→py-2, 히어로 섹션 패딩 축소
  - 하단 바로가기 3개(AI 파이프라인/응급 프로토콜/사용설명서)로 재구성
  - 점수 계산식 섹션 추가 (getRiskScoreFormula() 호출)

- `src/app/page.dashboard/view.ts` — 2건 수정
  - `currentEngineLabel()`: `(RandomForest + YOLOv8n)` → `(YOLO + RandomForest)`
  - `getRiskScoreFormula()` 메서드 신규 추가 (모델별 계산식 문자열 반환)

### RF threshold 조정 (FN-0004)
- `src/model/struct/video_analysis.py` — `fall_decision_threshold` 0.6 → 0.5
- `scripts/evaluate_models.py` — `RF_THRESHOLD` 0.6 → 0.5

### 정밀 평가 스크립트 (FN-0009~0010)
- `scripts/evaluate_rf_detailed.py` — 신규 생성
  - Y/N 각 250개씩 RF 파이프라인 분석, 100개마다 중간 결과 출력
  - 혼동행렬(TP/TN/FP/FN), 오탐 평균 위험점수 표시
- `scripts/evaluate_xgb_detailed.py` — 신규 생성
  - Y/N 각 250개씩 XGBoost(PF) 파이프라인 분석, 100개마다 중간 결과 출력

### FN-0011: view.ts 오류 확인
- 실제 코드 오류 없음. VS Code 모듈 해석 경고(`@angular/core`, `@wiz/libs/...`)만 존재 — Wiz 빌드 환경에서는 정상.
