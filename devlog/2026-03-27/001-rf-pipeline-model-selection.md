# RF 파이프라인 모델 추가 및 모델 선택 UI 구현

- **ID**: 001
- **날짜**: 2026-03-27
- **유형**: 기능 추가

## 작업 요약
기존 Person-Feature (XGBoost) 파이프라인 외에, YOLOv8n 사람 검출 → 16개 통계 특징 → RandomForest 분류 파이프라인(RF 파이프라인)을 추가하고, 사용자가 대시보드에서 분석 모델을 선택할 수 있는 UI를 구현했다. `_predict_behavior_from_runtime()`에서 inference=None 시 NoneType 에러 발생 버그도 수정.

## 변경 파일 목록

### 백엔드 (video_analysis.py)
- `_RF_MODEL_PATH`, `_RF_YOLO_MODEL`, `_RF_TARGET_FPS`, `_RF_CONF_THRES`, `_RF_PERSON_CLASS_ID`, `_RF_FEATURE_COLUMNS` 클래스 상수 추가
- `_rf_pipeline_available()`: RF 모델 파일 존재 확인
- `_infer_rf_pipeline()`: RF 파이프라인 추론 메서드 (~230줄)
- `_infer_with_trained_model()`: `model_type` 파라미터 추가, 'rf-pipeline'/'auto'/'legacy' 라우팅
- `_model_options()`: 사용 가능 모델 목록 반환
- `prototype_info()`: model_options 필드 추가
- `analyze_upload()`: metadata에서 model_type 추출, RF 파이프라인 독립 코드 경로 추가, speed_note 처리
- `_predict_behavior_from_runtime()`: inference=None 방어 코드 추가 (버그 수정)

### 프론트엔드 (view.ts)
- `selectedModelType` 상태 변수 추가
- `setModelType()` 메서드 추가
- `loadPrototypeInfo()`: model_options 기본값 설정
- `analyze()`: metadata에 model_type 전달
- `statusBadgeClass()`: 'rf-pipeline-runtime' 지원

### 프론트엔드 (view.pug)
- 분석 설정 세션에 모델 선택 버튼 행 추가 (모델 2개 이상 시 표시)

## 테스트 결과
- `prototype_info` API: 200 OK, model_options에 auto/legacy/rf-pipeline 3개 옵션 반환
- RF 파이프라인 분석: 200 OK, runtime_key=rf-pipeline-runtime, risk_score=0.9339, fall_detected=True (9.22초)
- Legacy 분석: 200 OK, 기존 동작 정상 유지

## 비고
- 파일 크기 96KB 초과 시 MCP 도구 파일 쓰기에서 truncation 발생할 수 있음. 터미널 `cat >>` append 방식으로 우회 가능.
- 디스크 공간 부족 시 storage/alerts 클립 파일 정리 필요.
