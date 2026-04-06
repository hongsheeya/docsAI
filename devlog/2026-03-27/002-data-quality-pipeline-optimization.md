# 데이터 품질 개선, 파이프라인 최적화, UI 리밸런싱

- **ID**: 002
- **날짜**: 2026-03-27
- **유형**: 기능 추가 · 버그 수정 · 리팩토링

## 작업 요약
FN-0007~0015 (9개 작업) 일괄 수행. 학습 데이터 분할 비율 수정(256:64), 메트릭 100% 문제 문서화 및 진단 경고 추가, 행동 분류 규칙 기반 명시, RF 파이프라인 분석 시간 최적화(모델 캐싱+배치 predict+fast FPS 하향), 실시간 웹캠 듀얼 레코더 오버래핑, 대시보드 결과 UI 좌우 균형 조정, 파이프라인 페이지 전면 개편(학습 과정 시각화·RF 흐름도·fast/balanced 비교 카드), 검증 리포트 섹션 제거, 모델 선택 동작 검증.

## 변경 파일 목록

### 백엔드 - 모델/분석
- `src/model/struct/video_analysis.py`
  - `_trained_model_info`: train_ratio, split_note, metric_source, evaluation_source, eval_accuracy, eval_f1, data_quality_issues 필드 추가
  - `_analysis_diagnostics`: 학습/검증 메트릭 괴리 경고 + 데이터 품질 이슈 진단 추가
  - `_behavior_state`: model_type='rule-based', model_type_label, model_type_note 추가
  - `_model_explanation` 행동 분류 카드: model_type 관련 필드 추가
  - RF 파이프라인: YOLO/RF 모델 클래스 레벨 캐싱 (`_get_rf_model`, `_get_rf_yolo_model`)
  - `_infer_rf_pipeline`: 배치 predict, fast 프로파일 FPS=1/최대 15프레임, target_fps 적응형
  - 진단 문자열 `%` 포맷 이스케이프 수정 (`100%` → `100%%`)

### 학습 데이터
- `storage/training/fall-detection/model/training_summary.json`
  - train_count 128→256, val_count 32→64, train_ratio 0.8
  - metric_source: training-epoch-final, evaluation.average → validation_report 값
  - data_quality_issues 배열 추가

### 프론트엔드 - 대시보드
- `src/app/page.dashboard/view.ts`
  - 듀얼 MediaRecorder (2초 오버랩) 오버래핑 분석
  - 청크 큐잉(최대 1건) + 낙상 검출 중복 방지 (4초 dedup window)
  - stopRealtimeAnalysis: 듀얼 레코더 정리
- `src/app/page.dashboard/view.pug`
  - 분석 워크스페이스 그리드: 1.28:0.72 → 1.1:0.9
  - 결과 그리드: unequal → `lg:grid-cols-2`
  - 판단 근거를 좌측 컬럼으로 이동

### 프론트엔드 - 파이프라인
- `src/app/page.pipeline/view.pug`
  - 데이터 학습 과정 5단계 시각화 (수집→전처리→라벨링→학습→평가)
  - RF 파이프라인 흐름도 (영상→YOLOv8n→16 features→RandomForest→위험도)
  - Fast vs Balanced 비교 카드
  - 학습 모델 섹션에 metric_source 경고 배너, 실제 검증 결과 블록 추가
  - 검증 리포트 섹션 삭제
  - 그리드 `xl:grid-cols-2` 균등 배치
