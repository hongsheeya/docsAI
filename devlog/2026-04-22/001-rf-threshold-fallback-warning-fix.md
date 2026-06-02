# RF threshold 재조정 및 fallback-warning 분리

- **ID**: 001
- **날짜**: 2026-04-22
- **유형**: 버그 수정

## 작업 요약
RF-Dual 업로드 분석에서 낙상 이진 모델이 민감하게 보이던 원인을 추적한 결과, 실제 RF 모델 재학습이 아니라 낮은 runtime confirm threshold(0.35)와 청크 추론 실패 시 heuristic fallback이 낙상처럼 기록되는 구조가 핵심 원인으로 확인되었다.
이에 따라 RF runtime confirm threshold 하한을 0.41로 상향하고, heuristic fallback은 절대 최종 낙상 판정을 내리지 못하도록 변경했으며, 청크 로그는 fallback-warning 타입으로 분리했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - RF confirm threshold 하한값 0.41 적용
  - heuristic fallback 결과를 `fall_detected=false`, `decision_state=fallback-warning`으로 고정
  - chunk 로그에 `log_type=fallback-warning` 추가
  - 분할 로그 최고 위험 요약에서 fallback-warning 로그 제외
  - fallback 상태 라벨을 `Fallback 경고`로 표시
- `storage/training/fall-detection/rf-pipeline/training_summary.json`
  - runtime tuned threshold 메타데이터를 0.41/0.30/0.56으로 정리
  - 운영 안전화 조정 note 반영

## 확인 결과
- 저장된 기존 업로드 메타를 재검토한 결과, 비낙상(N) 파일의 최종 `last_analysis.fall_detected=true` 사례는 확인되지 않았다.
- 문제는 주로 청크 레벨에서 runtime 실패 후 fallback이 낙상처럼 보이는 기록/표시 구조에 있었다.
- 현재 코드 기준으로 fallback은 최종 낙상 판정을 생성하지 않으며, 경고 로그로만 남는다.
