# 업로드 지연 및 앉기/서기 편향 완화

- **ID**: 008
- **날짜**: 2026-04-21
- **유형**: 버그 수정

## 작업 요약
업로드 모드 응답이 과도하게 느려지는 원인이던 추가 청크 재추론을 비활성화하고, 최근 외부 데이터 확장 학습에서 생긴 stand 편향을 줄이도록 약한 stand 매핑을 제거했다.
또한 런타임 자세 보정 규칙에서 sit→stand 강제 전환을 완화하고 stand→sit 복구 조건을 보강한 뒤 XG-Posture 모델을 재학습했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - 업로드 입력에서 추가 청크 분석을 비활성화하여 단일 패스로 응답하도록 조정
  - 외부 약한 액션의 stand 매핑 제거
  - sit→stand override 가드 강화 및 stand→sit 복구 신호 보강
- `storage/training/fall-detection/xg-posture/training_summary.json`
  - 외부 데이터 재선별 및 재학습 결과 반영
- `storage/training/fall-detection/xg-posture/xg_posture_model.pkl`
  - 완화된 매핑 규칙 기준으로 재학습된 모델 반영

## 결과 메모
- 외부 보조 데이터 class 분포가 `stand 220 → 5`, `sit 260 유지`로 재조정되었다.
- 재학습 후 전체 학습 샘플은 1620개, CV accuracy는 0.8994, train accuracy는 0.979로 기록되었다.
- 업로드 경로는 추가 청크 재추론을 수행하지 않으므로 응답 시간이 이전보다 크게 줄어들도록 정리했다.
