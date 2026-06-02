# 외부 person 액션 라벨 기반 XG-Posture 보조학습 추가

- **ID**: 006
- **날짜**: 2026-04-21
- **유형**: 기능 추가

## 작업 요약
- 외부 한국형 비전 데이터셋 Validation 라벨(JSON)에서 person keypoint와 action 라벨을 읽어 XG-Posture 재학습 보조 샘플로 사용할 수 있도록 확장했다.
- 현재 데이터셋에서 직접 매핑 가능한 `sit`, `walk` 라벨만 선별하고, 단일 이미지 keypoint를 정적 pose feature row로 변환해 기존 영상 윈도우 학습 데이터에 합쳤다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - 외부 데이터셋 경로/클래스 매핑 상수 추가
  - 외부 JSON 라벨을 XG-Posture feature row로 변환하는 helper 추가
  - `retrain_xg_posture()`가 외부 보조 샘플을 포함하고 legacy summary 키(`n_windows`, `cv_accuracy` 등)도 함께 기록하도록 보강
- `scripts/retrain_xg_posture_external.py`
  - WIZ 최소 stub 환경에서 XG-Posture 재학습을 터미널에서 직접 실행하는 스크립트 추가
- `devlog.md`
  - 2026-04-21 작업 이력 006 추가