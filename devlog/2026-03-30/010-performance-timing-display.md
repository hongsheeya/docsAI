# 성능 최적화 및 단계별 타이밍 표시

- **ID**: 010
- **날짜**: 2026-03-30
- **유형**: 기능 추가

## 작업 요약
RF 파이프라인 YOLO predict에 GPU 자동 감지(torch.cuda.is_available()) 추가. 단계별 타이밍(model_load, frame_extract, yolo_predict, feature_extract, rf_predict)을 UI에 시각화하는 컴포넌트 추가. api.py reference_preview에 os.path.exists 안전 검사 추가.

## 변경 파일 목록

### 백엔드
- `src/model/struct/video_analysis.py`
  - _get_yolo_device: GPU 자동 감지 classmethod 추가
  - _infer_rf_pipeline: yolo_model.predict에 device 파라미터 전달, 응답에 device 정보 포함

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - getStepTimings(): ratio 필드 추가 (전체 대비 비율)
- `src/app/page.dashboard/view.pug`
  - 낙상 감지 여부 카드 하단에 단계별 타이밍 바 추가 (도트 인디케이터 + 라벨 + 소요시간)
- `src/app/page.dashboard/api.py`
  - import os 추가, reference_preview에 os.path.exists 검사 추가
