# 웹 분석 파이프라인 person-feature 통합

- **ID**: 020
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
사람 추적 기반 특징 분석(person-feature) 파이프라인을 웹 분석 시스템에 통합했다. yolo_fall_runtime.py에 `--mode person-feature` 옵션을 추가하고, video_analysis.py에서 person_detector + fall_classifier 모델이 모두 존재하면 자동으로 person-feature 파이프라인을 우선 사용하도록 변경했다. 대시보드 UI에서 person-feature-runtime 결과를 올바르게 표시하도록 수정했다.

## 변경 파일 목록

### 백엔드 (scripts/)
- `scripts/yolo_fall_runtime.py`: person-feature 모드 추가
  - `--mode` 인자 (yolo-cls / person-feature) 추가
  - `_compute_window_features()`, `_person_feature_infer()`, `command_infer_person_feature()` 함수 추가
  - FEATURE_COLS 정의, sliding window 기반 tracking → feature 추출 → XGBoost 분류 파이프라인

### 백엔드 (model/)
- `src/model/struct/video_analysis.py`:
  - `_runtime_python_path()`: `.venv-yolo` 삭제 대응, `/opt/conda/envs/app/bin/python` 폴백 및 `shutil.which` 폴백 추가
  - `_person_feature_available()`: baseline_model.json에서 person_detector + fall_classifier 존재 여부 확인
  - `_infer_with_trained_model()`: person-feature 가용 시 자동 분기 (기존 YOLO-cls 폴백 유지)
  - `_infer_yolo_cls()`: 기존 YOLO 분류 추론 로직 분리
  - `_infer_person_feature()`: person-feature 런타임 호출 + 결과 후처리 (top_windows→events, top_features→analysis_basis)
  - `analyze_upload()` 내 analysis_basis, analysis_speed_note에 person-feature-runtime 케이스 추가

### 프론트엔드
- `src/app/page.dashboard/view.ts`: statusBadgeClass에 'person-feature-runtime' 추가
- `src/app/page.dashboard/view.pug`: analysis_basis가 객체(label+value) 형태도 지원하도록 수정

## 테스트 결과
- 낙상 영상(Y): fall_detected=true, score=0.665, probability=0.99, 40.6초 소요
- 비낙상 영상(N): fall_detected=false, score=0.372, probability=0.655, 40.1초 소요
- 빌드: 정상 완료 (5.2초)
