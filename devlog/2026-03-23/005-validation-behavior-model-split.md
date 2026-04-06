# Validation 70/30 기반 6종 행동 분류 모델 분리

- **ID**: 005
- **날짜**: 2026-03-23
- **유형**: 기능 추가

## 작업 요약
Validation 데이터를 기준으로 6종 행동 분류 모델을 별도 학습 구조로 분리하고, 메인 분석 결과에 행동 라벨을 함께 노출하도록 정리했다.

## 변경 파일 목록
- `src/model/libs/action_behavior_model.py`
- `src/model/struct/video_analysis.py`
