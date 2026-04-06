# XG-Posture 재훈련 (KTH 데이터 통합)

- **ID**: 023
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
KTH Action Recognition Dataset(walk 81, run 80)을 XG-Posture 학습 데이터에 통합하고 재훈련 실행. Intake 경로 불일치(`_appdata/data/storage/` vs `_appdata/storage/`) 발견 및 해결 후 141 샘플로 4-class 모델 학습 완료 (CV F1 macro = 86.19%).

## 주요 이슈: Intake 경로 불일치
- **다운로드 스크립트**: `PROJECT_ROOT/data/storage/...` → `_appdata/data/storage/.../intake/`
- **학습 코드**: `wiz.project.fs().abspath()/storage/...` → `_appdata/storage/.../intake/`
- **해결**: correct intake 경로로 데이터 수동 복사 + posture 디렉토리(walk/run/stand/sit/lie/fall) 생성

## 학습 결과
| 지표 | 값 |
|------|-----|
| 모델 | xg-posture-37 (XGBClassifier) |
| 학습 샘플 | 141 (stand:10, walk:69, run:52, fall:10) |
| 활성 클래스 | 4 (stand, walk, run, fall) |
| CV Accuracy | 84.4% |
| CV F1 Macro | 86.19% |
| Train Accuracy | 100% |
| 상태 | Ready: True |

## 스킵된 데이터
- KTH 클립 일부(160x120 저해상도)에서 bbox 감지 실패 → walk 12/81, run 28/80 스킵
- 정상 동작이며, 해상도가 낮은 클립은 피처 추출 불가로 자동 제외됨

## 변경 파일 목록
### 데이터
- `_appdata/storage/training/fall-detection/intake/walk/` — 81 clips (KTH walking)
- `_appdata/storage/training/fall-detection/intake/run/` — 80 clips (KTH running)
- `_appdata/storage/training/fall-detection/intake/fall/` — 20 clips (from Y/)
- `_appdata/storage/training/fall-detection/intake/stand/` — 20 clips (from N/)
- `_appdata/storage/training/fall-detection/intake/sit/` — 0 (empty, 추후 수집)
- `_appdata/storage/training/fall-detection/intake/lie/` — 0 (empty, 추후 수집)

### 모델 산출물
- `xg-posture/xg_posture_model.pkl` — 학습된 모델
- `xg-posture/training_summary.json` — 학습 요약
