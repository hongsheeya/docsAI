# HITL 재학습 하드 타임아웃 제거 및 증분 최적화

- **ID**: 007
- **날짜**: 2026-04-01
- **유형**: 버그 수정 + 성능 최적화

## 작업 요약
사용자 피드백에 따라 HITL 재학습의 하드 타임아웃을 제거했다. 대신 학습은 끝까지 진행되도록 유지하면서, intake feature 추출을 증분 캐시 방식으로 전환하고 fast profile을 사용해 재학습 시간을 줄였다. 또한 baseline 재학습은 전체 rebuild 대신 캐시 재사용 기반으로 동작하도록 조정하고, 교차검증 fold 수와 불필요한 모델 저장 비용을 줄였다.

## 변경 파일 목록

### Backend — src/model/struct/video_analysis.py
- `retrain_baseline()`에서 threading 기반 강제 타임아웃 제거
- baseline/behavior 재학습을 `force_rebuild=False`로 호출해 intake feature 캐시 재사용
- baseline/behavior 소요 시간을 `timings`로 반환

### Backend — src/model/libs/video_baseline.py
- HITL feature 추출 프로파일을 `balanced` → `fast`로 변경
- `intake_features.csv` + `intake_manifest.json`를 이용한 증분 append 캐시 추가
- 신규 feedback 영상만 추출하고 기존 영상 feature는 재사용
- 교차검증 fold 수를 데이터가 많을 때 5 → 3으로 축소
- best model만 재학습/저장하고 나머지 후보 모델 재저장 제거

### Frontend — src/app/page.dashboard/view.ts
- 재학습 타임아웃 전용 실패 문구 제거
- 장시간 재학습 경고 메시지는 유지
