# 레거시 YOLO 분류 모델 제거

- **ID**: 008
- **날짜**: 2026-03-30
- **유형**: 리팩토링

## 작업 요약
레거시 YOLO 분류 모델(trained-yolo-runtime) 전체 제거. auto 모드 fallback 순서를 rf-pipeline → person-feature로 정리. legacy/yolo-cls/trained-yolo 키 입력 시 rf-pipeline으로 호환 리디렉트. _infer_yolo_cls 메서드 제거, _model_options에서 legacy 항목 삭제, 프론트엔드 engineMap/noteMap에서 legacy 제거.

## 변경 파일 목록

### 백엔드
- `src/model/struct/video_analysis.py`
  - _infer_with_trained_model: legacy/yolo-cls → rf-pipeline 호환 매핑, trained-yolo 항목 제거
  - _infer_yolo_cls: 전체 메서드 삭제 (~115줄)
  - _model_options: legacy 항목 제거, auto 설명 갱신
  - _model_option_label: legacy/trained-yolo 라벨 제거
  - _trained_model_info: trained-yolo-runtime fallback 제거
  - _risk_score_detail: trained-yolo-runtime 분기 제거
  - _analysis_engine_summary: trained-yolo-runtime fallback → person-feature
  - analyze_upload: trained-yolo-runtime speed_note/analysis_overview 블록 제거

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - currentEngineLabel/currentEngineNote에서 legacy 키 제거
  - statusBadgeClass에서 trained-yolo-runtime 제거
