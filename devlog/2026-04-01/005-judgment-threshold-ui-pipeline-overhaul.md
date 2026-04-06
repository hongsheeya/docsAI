# 판단 기여도 정렬·임계값 정합성·UI/파이프라인 전면 개선 (FN-0023~0029)

- **ID**: 005
- **날짜**: 2026-04-01
- **유형**: 기능 추가 / 버그 수정 / UI 개선

## 작업 요약
FN-0023~0029 7개 작업을 일괄 수행. RF/XGBoost 판단 근거를 기여도 순 정렬, RF 임계값 일관성 버그 수정, XGBoost 점수 비중 재조정 및 threshold 0.5 분리, HITL 재학습 타이밍 표시, 분석 시간 동적 안내, 대시보드 UI 정리, 파이프라인 페이지 전면 현행화.

## 변경 파일 목록

### 백엔드 (Python)
- **src/model/struct/video_analysis.py**
  - FN-0023: RF `analysis_basis`에 `_sort_score` 추가, importance×|value| 기준 내림차순 정렬
  - FN-0023: XGBoost `_xgb_basis_items`에 feature importance 기반 기여도 정렬 + "기여도 X%" 라벨
  - FN-0028: `fall_detected = pred == 1` → `fall_detected = score >= self.fall_decision_threshold` (바이너리 예측→확률 기준)
  - FN-0029: `_PERSON_FEATURE_THRESHOLD = 0.5` 클래스 변수 추가, XGBoost 독립 임계값 분리
  - FN-0029: `_risk_score_guide()` person-feature 임계값 반영
  - FN-0029: `analyze_upload()` 최종 판정 근거에 파이프라인별 임계값 동적 표시

- **scripts/yolo_fall_runtime.py**
  - FN-0029: `final_score` 산식 확장 — `floor_proximity` boost (0.10 가중), `height_ratio` boost (0.05 가중) 추가
  - FN-0029: motion gate `floor_proximity` 기준 0.82→0.78 완화, `_floor_height_override` 추가 (fp≥0.85 + hr≤-0.08이면 게이트 우회)

### 프론트엔드 (TypeScript)
- **src/app/page.dashboard/view.ts**
  - FN-0024: `retrainElapsedSec`, `retrainStartedAt`, `retrainFinishedAt`, `retrainTimerHandle` 추가, 재학습 중 1초 간격 경과 시간 표시, 완료 시 소요 시간 + 시각 표시
  - FN-0025: `modelSpeedHint()` — 영상 길이 기반 동적 예상 시간 계산 (60초 이상 영상은 비례 증가)
  - FN-0024: `ngOnDestroy()`에 retrain timer 정리 추가

### 프론트엔드 (Pug)
- **src/app/page.dashboard/view.pug**
  - FN-0026: 상단 hero 카드 4열→3열, `fall_model_label` 제거, 실시간 상태 동적 색상
  - FN-0026: "Live Preview"→"Video Input", "PREVIEW"→"LOADED/EMPTY"
  - FN-0026: "분석 설정"→"모델 선택", 프로파일 선택기·"분석 모델" 라벨 제거
  - FN-0027: pipeline page header "빠른/정밀 분석 차이" 문구 제거

- **src/app/page.pipeline/view.pug** (전면 재작성)
  - FN-0027: XGBoost ByteTrack 파이프라인 흐름도 추가 (violet 테마, 7단계)
  - FN-0027: "빠른 분석 vs 정밀 분석" → "RF vs XGBoost 비교" (실제 두 엔진 특성 비교)
  - FN-0027: F1/AUC 영역 `*ngIf="metric_ready"` 조건부 표시, 미준비 시 모델 기본 정보 표시
