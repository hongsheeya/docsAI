# 전체 행동 분류 런타임 재평가 및 서기 스케일 보정

- **ID**: 005
- **날짜**: 2026-04-20
- **유형**: 버그 수정, 검증

## 작업 요약
현재 RF-Dual 자세 분류가 실제 런타임에서 제대로 동작하는지 6개 행동 클래스(`stand`, `walk`, `run`, `sit`, `lie`, `fall`) 샘플을 다시 평가했다. 그 결과 수정 전에는 `stand` 재현율이 0으로, 서기 샘플 8개가 전부 `sit/lie`로 무너지는 심각한 회귀가 확인됐다. 원인을 추적해 보니 후처리에서 사용하던 `pose_height_ratio_mean` 임계값이 실제 런타임 feature 스케일보다 훨씬 높아 `stand rescue`가 거의 발동하지 못했다. 이를 실제 스케일(stand 약 0.33 전후)에 맞춰 조정하고, `상체 수직 + 무릎 펴짐 + 보행 리듬 없음` 조건의 강한 `stand prior boost`를 추가했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - `upright_posture` / `stand_ready`의 `pose_height` 기준을 실제 런타임 스케일에 맞춰 완화
  - `hard_stand_evidence` 규칙 추가: 상체 수직, 하체 직립, gait 없음이면 `sit/lie/walk/run -> stand` 강제 복구
  - stand gain / rescue transfer cap 상향

## 검증 결과
- 샘플 런타임 재평가(클래스당 최대 8개, 총 48개 시도)에서 수정 전 `stand` 재현율 **0.000 → 수정 후 0.625 (5/8)** 로 개선
- 같은 샘플 평가에서 아직 `walk/run`은 별도 문제가 남아 있음(검출 실패 + posture 모델 편향)
- 검출 실패 케이스도 다수 확인되어, 전체 행동 분류 품질 이슈는 `posture 후처리`와 `YOLO pose 검출 안정성` 두 축으로 나뉨

## 산출물
- 임시 런타임 평가 결과: `tmp_posture_eval_runtime_sample.json`
