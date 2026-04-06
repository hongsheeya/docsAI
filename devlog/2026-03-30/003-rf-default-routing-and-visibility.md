# RF 파이프라인 v2 기본 운영 모델 전환 및 표시 정합성 보정

- **ID**: 003
- **날짜**: 2026-03-30
- **유형**: 기능 추가

## 작업 요약
사람 추적 기반 XGBoost 경로의 실사용 정확도가 낮다는 운영 판단에 맞춰, 자동 선택 모드의 기본 우선순위를 RF 파이프라인 v2로 전환했다. 동시에 대시보드와 모델 설명 카드에서 RF 파이프라인을 더 이상 구버전으로 표기하지 않도록 정리하고, RF 메트릭 파일이 없을 때는 잘못된 XGBoost CV 수치를 보여주지 않도록 구조 메타데이터 중심으로 표시를 보정했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
  - `auto` 모델 선택 우선순위를 `rf-pipeline -> person-feature -> trained-yolo`로 변경
  - 기본 분석 엔진 요약, 모델 옵션, 설명 카드, 실제 적용 모델 라벨을 RF 파이프라인 v2 기준으로 정리
  - RF 모델 파일에서 트리 수·특징 수·수정 시각을 읽는 `_rf_runtime_meta()` 추가
  - RF 모델 로더에 `/opt/app/my_libs` 경로 보강을 추가해 sklearn 의존성 로딩 안정화
- `src/app/page.dashboard/view.pug`
  - 실제 적용 모델 카드에서 RF 메트릭 유무에 따라 CV 정보 또는 구조 정보(트리/특징 수)를 표시하도록 수정
- `devlog.md`
  - 2026-03-30 작업 요약 행 추가

## 검증
- RF 모델 메타 점검: `RandomForestClassifier`, 16 features, 200 trees 확인
- normal build 성공
