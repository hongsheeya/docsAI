# HITL 재학습 경로 복구 및 실제 적용 모델 표시 강화

- **ID**: 002
- **날짜**: 2026-03-30
- **유형**: 기능 추가

## 작업 요약
HITL 피드백이 intake 폴더에만 저장되고 실제 XGBoost 재학습에는 반영되지 않던 문제를 확인했다. `video_baseline.py`를 placeholder에서 실제 재학습 파이프라인으로 교체해 intake 영상에서 사람 추적 feature를 추출하고, 기존 학습 데이터와 병합한 뒤 분류기를 다시 학습할 수 있도록 수정했다. 동시에 분석 결과 화면에 요청 모델과 실제 적용 모델을 함께 노출하도록 보강했다.

## 변경 파일 목록
- `src/model/libs/video_baseline.py`
  - intake 영상 → person detector tracking → 10개 feature 추출 → 기존 데이터 병합 → LR/RF/XGBoost 재학습 경로 구현
  - `hitl-features/intake_features.csv`, `intake_manifest.json` 생성 지원
- `src/model/struct/video_analysis.py`
  - 모델 옵션 라벨 helper 추가
  - pipeline 설명을 실제 운영 순서(person-feature → YOLO → RF) 기준으로 정리
  - 분석 결과에 요청 모델 / 실제 적용 모델 정보 추가
- `src/app/page.dashboard/view.pug`
  - 분석 모드 카드에 요청 모델 / 실제 적용 모델 표시
  - 현재 연결된 모델 정보 섹션을 실제 적용 모델 중심으로 정리

## 검증
- HITL feature 병합 경로 확인: 총 2288 rows, intake 38 rows, intake videos 2건
- normal build 성공
