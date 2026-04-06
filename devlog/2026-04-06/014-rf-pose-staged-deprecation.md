# RF-Pose 단계적 삭제 (deprecate → shadow → hard delete 준비)

- **ID**: 014
- **날짜**: 2026-04-06
- **유형**: 리팩토링

## 작업 요약
XG-Dual 체계 안정화에 따라 RF-Pose를 3단계에 걸쳐 폐기하는 구조를 구현하였다.
Stage A(UI에서 숨김), Stage B(shadow mode 비교 로깅), Stage C(삭제 승인 조건 체크) 완료.
실제 코드 삭제(hard delete)는 shadow 데이터 충분 축적 후 수동 승인으로 진행된다.

## 변경 파일 목록

### Stage A — deprecate (UI 숨김)
- `src/model/struct/video_analysis.py`
  - `_model_options()`: rf-pose 옵션을 options 목록에서 제거, xg-dual/xg-fall 옵션 추가, default를 xg-dual로 변경
  - `_model_option_label()`: xg-dual/xg-fall 라벨 추가, rf-pose에 '(deprecated)' 표기
  - `_infer_with_trained_model()`: default model_type을 'xg-dual'로 변경, auto fallback에서 rf-pose 제외
  - `retrain_baseline()`: rf-pose 재학습 단계를 스킵 (코드는 유지)
  - `_infer_rf_pose_pipeline()`, `retrain_rf_pose_pipeline()`: docstring에 DEPRECATED 마킹
- `src/app/page.dashboard/view.ts`
  - `currentEngineLabel()`, `currentEngineNote()`: default를 xg-dual로 변경, xg-fall 엔트리 추가, rf-pose에 deprecated 표기

### Stage B — shadow mode
- `src/model/struct/video_analysis.py`
  - `_shadow_compare_rf_pose()`: XG-Dual 추론 시 RF-Pose를 백그라운드 실행하여 비교 로그를 JSONL로 저장
  - `shadow_comparison_report()`: 지정 기간의 shadow 로그를 분석하여 agreement rate, score diff 등 통계 + 삭제 승인 조건 체크
  - `_infer_xg_dual()`: 추론 완료 후 shadow 비교 자동 실행 (try/except 래핑으로 non-blocking)
- `src/app/page.dashboard/api.py`
  - `shadow_report()`: shadow comparison report API 엔드포인트 추가

### Stage C — hard delete 준비
- `src/model/struct/video_analysis.py`
  - `rf_pose_deletion_status()`: 삭제 승인 조건 충족 여부 점검 함수 (shadow 데이터 30건 이상, agreement ≥ 90%, avg score diff ≤ 0.15)
  - `_get_rf_pose_model_path()`: 모델 파일 경로 헬퍼
- `src/app/page.dashboard/api.py`
  - `rf_pose_deletion_status()`: 삭제 준비 상태 확인 API 엔드포인트

### Stage D — 보존 목록
- pose feature 계산 유틸 (`_extract_pose_features`, XG 통합 추출기 내 keypoint 처리)
- keypoint validation / confidence filtering 로직
- XG 37-feature 공통 추출기 (`_extract_unified_timeseries`, `_build_xg_feature_windows`)
