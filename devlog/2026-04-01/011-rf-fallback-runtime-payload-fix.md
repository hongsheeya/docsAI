# RF fallback 런타임 payload 변수 누락 수정

- **ID**: 010
- **날짜**: 2026-04-01
- **유형**: 버그 수정

## 작업 요약
RF 추론 리팩토링 후 `model_runtime` payload에서 이미 제거된 지역변수 `target_fps`, `yolo_imgsz`를 계속 참조하고 있어 RF 추론 완료 직전 NameError가 발생했다. 이 예외가 상위에서 잡히며 fallback 분석으로 전환되고 있었다. 상수/활성 모델 경로를 사용하도록 수정해 RF 추론이 정상 반환되게 복구했다.

## 변경 파일 목록

### Backend — src/model/struct/video_analysis.py
- `model_runtime.rf_model_path`를 활성 RF 모델 경로로 수정
- `model_runtime.yolo_imgsz`, `model_runtime.target_fps`를 제거된 지역변수 대신 클래스 상수 사용으로 수정
