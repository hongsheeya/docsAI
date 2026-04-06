# YOLO 모델 웹 통합 및 낙상영상 검증

- **ID**: 007
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
학습된 YOLO 분류 모델을 웹 애플리케이션 백엔드에 통합하고, 프론트엔드 UI에 학습 데이터 및 모델 정보를 표시하도록 구현. `/opt/app/낙상영상` 데이터셋(Y: 5, N: 7)으로 모델 검증을 수행하여 과적합 문제를 확인함.

## 변경 파일 목록

### 신규 생성
- `scripts/yolo_fall_runtime.py`: YOLO 추론/평가 런타임 스크립트 (유니코드 NFD/NFC 정규화 처리 포함)

### 백엔드 수정
- `src/model/struct/video_analysis.py`: `_yolo_runtime_inference()` 메서드 추가, `analyze_upload()`에서 YOLO 우선 추론, `prototype_info()`에 학습 정보 포함, `_model_explanation()` 학습 메트릭 표시

### 프론트엔드 수정
- `src/app/page.dashboard/view.ts`: trained-yolo-runtime 뱃지 클래스 추가
- `src/app/page.dashboard/view.pug`: YOLO 학습 모델 상세 섹션 추가
- `src/app/page.pipeline/view.ts`: trained-yolo-runtime 뱃지 클래스 추가
- `src/app/page.pipeline/view.pug`: YOLO 학습 모델 상세 섹션 추가
- `src/app/page.admin.analysis/view.ts`: trained-yolo-runtime 뱃지 클래스 추가
- `src/app/page.admin.analysis/view.pug`: YOLO 학습 모델 상세 섹션 추가

### 검증 결과
- `storage/training/fall-detection/model/validation_report.json`: 낙상영상 평가 리포트
- 정확도 45.5%, 재현율 100%, 정밀도 45.5% — 모든 비디오를 낙상으로 분류 (과적합)

## 기술 이슈
- 한글 디렉토리명 유니코드 NFD/NFC 정규화 문제 해결 (`_resolve_unicode_segments` 함수)
- `00002_H_A_N_C1.mp4` 파일 손상 (moov atom 누락) — 에러 핸들링으로 스킵 처리
- `00074_H_A_BY_C1.mp4` Y/N 폴더 동시 존재 (데이터 라벨 충돌)
