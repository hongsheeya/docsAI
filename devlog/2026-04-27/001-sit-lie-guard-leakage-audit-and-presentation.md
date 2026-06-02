# sit/lie 가드 보정, 데이터 누수 점검, 문서/발표자료 최신화

- **ID**: 001
- **날짜**: 2026-04-27
- **유형**: 버그 수정 / 문서 업데이트

## 작업 요약
RF-Dual posture 후처리에서 상체가 직립에 가까운 seated 장면이 `lie`로 과보정되던 경로를 줄이기 위해 `upright_sit_guard`를 추가하고 `lie rescue` 조건을 강화했다.
동시에 posture 학습 스크립트의 window-level CV가 clip-level 데이터 누수 위험이 있음을 확인해 group-aware CV로 변경했고, 운영 문서와 발표자료를 현재 RF-Dual 기준으로 최신화했다.

## 변경 파일 목록
### 모델 로직
- `src/model/struct/video_analysis.py`
  - `upright_sit_guard` 추가
  - `sit/stand -> lie` 보정 감산 강화
  - `lie -> sit` 복구 강화
  - `low_profile_lie` rescue 제한

### 학습 검증
- `/opt/app/scripts/train_posture_model.py`
  - `StratifiedGroupKFold` 우선, `GroupKFold` fallback 적용
  - clip-grouped CV 메타정보(`cv_mode`, `n_unique_clips`, `leakage_guard`) 저장

### 문서
- `README.md`
- `docs/prototype/fall-detection/README.md`
- `docs/label-system-data-strategy.md`
- `docs/xg-dual-architecture.md`
  - RF-Dual 최신 운영 기준 반영
  - raw 6-class / 운영 5-class 분리 반영
  - 레거시 문서 표시 및 누수 방지 메모 반영

### 발표자료
- `docs/presentation/2026-04-27-rf-dual-audit-deck.md`
  - 개요, 판단 파이프라인, RF-Dual 구조, 2모델 중첩 이유와 성능, 학습 현황, 데이터 수집/학습 방법, 한계점, 개선 방향 포함해 발표용 구조로 재작성
  - 실제 오분류 사례 3건, 수정 전후 비교표, 향후 실험 계획 표 추가

## 검증
- `python3 -m py_compile /opt/app/project/main/src/model/struct/video_analysis.py /opt/app/scripts/train_posture_model.py`
- `wiz project build --project=main`
- 문제 패널 기준 changed files error 없음 확인
