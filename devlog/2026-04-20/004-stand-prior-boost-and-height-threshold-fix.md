# 서기 prior 부스트 및 높이 임계값 보정

- **ID**: 004
- **날짜**: 2026-04-20
- **유형**: 버그 수정

## 작업 요약
서기가 계속 앉기로 무너지는 현상을 추가 조사한 결과, 후처리에 `stand`를 적극적으로 살리는 규칙이 거의 없고 `stand rescue`의 높이 비율 임계값도 과도하게 높아 실제 서 있는 장면이 조건을 통과하지 못하던 문제가 있었다. 이를 해결하기 위해 upright posture에 대한 `stand prior boost`를 새로 추가하고, stand rescue의 `pose_height` 기준을 현실적인 값으로 낮췄다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - upright posture(`pose_tilt`, `pose_height`, floor 관련 특징) 기반 `stand prior boost` 추가
  - `sit/lie -> stand` rescue의 `pose_height` 기준 완화 (`0.60/0.68` → `0.52/0.60`)
  - 서기 후보에서 하체 비가시 상황도 상체 수직/높이 유지 시 복구 가능하도록 보정

## 기대 효과
- 상체/하체가 정상적으로 보이는 서기 장면에서 stand가 더 잘 살아남음
- raw 확률이 sit 쪽으로 조금 기울어도 smoothing 전에 stand로 보정 가능
- 과도한 높이 임계값 때문에 stand rescue가 실패하던 현상 완화
