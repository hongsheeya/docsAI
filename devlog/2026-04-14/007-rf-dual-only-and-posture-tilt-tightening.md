# RF-Dual 전용 선택지 제한 및 sit/lie 경계 휴리스틱 보정

- **ID**: 007
- **날짜**: 2026-04-14
- **유형**: 기능 조정

## 작업 요약
대시보드에서 일반 모델 선택지를 일단 RF-Dual 단일 옵션으로 제한했다. 동시에 RF-Dual 내부의 XG-Posture 후처리에서 sit/lie 경계가 과하게 lie 쪽으로 기우는 문제를 줄이기 위해 상체 기울기, 바닥 밀착도, 높이 비율을 함께 보는 보수적 휴리스틱을 추가했다.

적용 후 기존 업로드셋을 재평가한 결과 낙상 FP/FN은 그대로 0/0을 유지했다. 과거 36건 공통 비교에서는 posture 변경이 16건 있었지만 모두 동일 원본(00110_H_A_N_C1.mp4)의 중복 업로드였고, lie → sit으로만 조정되었다.

## 변경 파일 목록
### 프론트엔드
- `src/app/page.dashboard/view.pug`
  - 웹캠/업로드 모델 선택 UI를 비활성화하고 RF-Dual 단일 옵션만 노출하도록 정리

### 백엔드
- `src/model/struct/video_analysis.py`
  - `_infer_with_trained_model()`에서 비-RF-Dual 요청을 RF-Dual로 강제 정규화
  - `_model_options()`를 RF-Dual 단일 옵션만 반환하도록 축소
  - `_posture_heuristic_boost()`에 sit/lie 경계 보정 규칙 추가

## 테스트 결과
- `python3 scripts/reevaluate_existing_uploads.py`
  - total 81, FP 0, FN 0
- export 기준 기존 36건과 공통 비교
  - posture 변경 16건
  - 변경 고유 원본 1건: `00110_H_A_N_C1.mp4`
  - 변경 방향: `lie -> sit`

## 비고
- sit/lie 보정은 fall score 자체를 건드리지 않고 posture 후처리만 조정하도록 제한했다.
- 업로드셋에서 낙상 회귀는 없어서 이번 조정은 유지했다.
