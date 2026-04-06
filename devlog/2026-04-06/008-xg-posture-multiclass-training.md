# XG-Posture multiclass 학습 파이프라인 구축

- **ID**: 008
- **날짜**: 2026-04-06
- **유형**: 기능 추가

## 작업 요약
XG-Posture 6-class multiclass (stand/walk/run/sit/lie/fall) 학습 메서드 `retrain_xg_posture()`를 video_analysis.py에 구현했다. posture별 디렉토리 또는 Y/N→fall/stand bootstrap 모드를 지원하며, 1.5s 윈도우로 37-feature 추출 후 XGBClassifier(multi:softprob)로 학습한다.

## 변경 파일 목록

### 수정: src/model/struct/video_analysis.py (5050 → 5245 lines, +195 lines)
- `_XG_POSTURE_CLASSES`: 6-class 리스트 상수
- `retrain_xg_posture()`: posture 디렉토리 탐색 → unified timeseries → 1.5s window → XGBClassifier(multi:softprob) 학습
  - Bootstrap 모드: Y→fall, N→stand 매핑으로 2-class에서 시작 가능
  - Active classes 동적 검출: 데이터 있는 클래스만 학습
  - CV(StratifiedKFold) + macro F1 + class-wise recall 기록
  - 모델을 `{model, classes, feature_cols}` dict로 저장 (클래스 매핑 메타데이터 포함)
