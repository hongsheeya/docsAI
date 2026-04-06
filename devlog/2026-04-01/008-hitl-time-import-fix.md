# HITL 재학습 time import 누락 수정

- **ID**: 008
- **날짜**: 2026-04-01
- **유형**: 버그 수정

## 작업 요약
`retrain_baseline()`에서 `time.time()`을 사용하도록 변경한 뒤 상단 `import time`이 누락되어 런타임에서 `name 'time' is not defined` 오류가 발생했다. 모듈 상단에 `import time`을 추가하고 빌드를 다시 검증했다.

## 변경 파일 목록

### Backend — src/model/struct/video_analysis.py
- `import time` 추가
- HITL 재학습 timing 로직의 런타임 NameError 해소
