# RF-Pose 25-feature HITL 학습 파이프라인 강화

- **ID**: 001
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
RF-Pose 25-feature 파이프라인의 HITL 피드백 데이터 축적·모니터링·자동 재학습 메커니즘을 강화하고, 재학습 시 3개 모델(Baseline/RF-Pipeline/RF-Pose) 간 A/B 성능 비교 리포트를 자동 생성하도록 구현했다.

## 변경 파일 목록

### 백엔드 (Model Struct)
- `src/model/struct/video_analysis.py`
  - `AUTO_RETRAIN_THRESHOLD = 10` 클래스 상수 추가
  - `_intake_summary()` 메서드 강화: 날짜별(`by_date`) / 소스별(`by_source`) 상세 통계, 마지막 재학습 이후 피드백 누적 건수(`since_last_train`) 추가
  - `submit_analysis_feedback()` 메서드에 자동 재학습 트리거 로직 추가: 마지막 학습 이후 N건 이상 피드백 누적 시 `retrain_baseline()` 자동 호출
  - `_build_model_comparison_report()` 신규 메서드: 재학습 후 Baseline/RF-Pipeline/RF-Pose 3모델 CV 메트릭 비교, 최적 모델 식별, RF-Pose vs RF-Pipeline 피처 확장 효과 분석
  - `retrain_baseline()` 반환값에 `model_comparison` 키 추가

### 프론트엔드 (Dashboard)
- `src/app/page.dashboard/view.ts`
  - `submitAnalysisFeedback()` 함수에 자동 재학습 결과 표시 분기 추가: `auto_retrain_triggered` 플래그 처리, 자동 재학습 사유 메시지 표시
