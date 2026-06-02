# 행동 분류용 pose 검출 재시도 체인 추가

- **ID**: 006
- **날짜**: 2026-04-20
- **유형**: 버그 수정, 검증

## 작업 요약
행동 분류 샘플을 다시 점검한 결과, 다른 클래스(`walk`, `run`, `sit`, `fall`)의 상당수는 분류기 자체 문제 이전에 **pose 타겟 검출 실패**로 시작되고 있었다. 원인을 추적해 보니 두 가지 축이 있었다. 첫째, 실제 사람은 보이지만 crop/augmentation 때문에 기본 설정(`conf=0.25`, 기본 샘플링)으로는 검출 프레임 수가 0~1로 부족한 케이스. 둘째, synthetic 일부는 pose/person detector가 어떤 설정에서도 전혀 사람으로 인식하지 못하는 도메인 미스매치 케이스였다. 이에 대해 우선 해결 가능한 첫 번째 축을 잡기 위해 unified timeseries 추출 단계에 **pose 검출 재시도 체인**을 넣었다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - `_extract_unified_timeseries()`에 프레임 재샘플링 helper 추가
  - 초기 pose 검출 프레임 수가 부족하면 낮은 conf / 큰 imgsz / 더 촘촘한 step으로 재시도
  - 재시도 결과는 `perf['pose_retry']`에 남기도록 추가

## 원인 분석
- **복구 가능 케이스**: crop된 KTH walk/run, 일부 sit/fall augmentation은 낮은 conf와 더 촘촘한 샘플링으로 검출 회복 가능
- **복구 어려운 케이스**: `synth_*` 일부는 `yolov8n-pose`, `yolov8n` 모두 사람을 전혀 잡지 못함 → detector domain mismatch. 이들은 데이터 정제/제외 대상

## 검증 결과
- 실패 샘플 개별 확인:
  - `aug2_run_kth_person15_running_d1_clip02_sub2.mp4`: `0~1 frame` → 재시도 후 `2 frame` 검출로 회복
  - `aug2_sit_aug_sit_20260414005825-dfcd7_cropped_cen_sub2.mp4`: `1 frame` → 재시도 후 `6 frame` 검출로 회복
- 샘플 기준 검출 가능 수(클래스당 8개):
  - 수정 후 `stand 8/8`, `walk 8/8`, `run 7/8`, `sit 8/8`, `lie 8/8`, `fall 7/8`
  - 총 검출 실패는 **48개 중 2개**만 남음
- 샘플 행동 분류 재확인 결과:
  - `walk` 재현율이 `0.000 → 0.375`로 개선
  - 남은 실패 2건은 synthetic detector-impossible 케이스

## 후속 제안
- `synth_*`처럼 detector-impossible 샘플은 posture 학습/평가 세트에서 자동 제외하는 정제 단계 추가 필요
- 이후 남은 `run`, `lie/fall` 경계는 분류/후처리 측면에서 추가 조정 필요
