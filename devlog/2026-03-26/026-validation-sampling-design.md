# Validation 200건 샘플링 및 밸런싱 설계

- **ID**: 026
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
Validation 데이터셋(2,272건)에서 추가학습용 200건을 Y/N 균형 샘플링하고, batch-001(100건)과 batch-002(100건)로 분할함. Y 내부 하위 클래스(FY/SY/BY)도 균등 배분하고, prefix(촬영 세션) 다양성을 최대화하는 샘플링 전략 수립.

## 변경 파일 목록

### 신규 스크립트
- `scripts/sample_validation_videos.py`: 전수 스캔 → 계층 샘플링 → 배치 분할 → 매니페스트 저장
- `scripts/train_validation_additional.py`: 통합 학습 파이프라인 (bbox 추출 → feature 추출 → XGBoost 학습 → YOLO 학습)

### 산출물
- `storage/training/fall-detection/validation-samples/batch-001.json`: 1차 배치 100건 매니페스트
- `storage/training/fall-detection/validation-samples/batch-002.json`: 2차 배치 100건 매니페스트
- `storage/training/fall-detection/validation-samples/sampling_manifest.json`: 샘플링 종합 설정

### 분석 결과
- 전체 Validation: Y=1704(FY:776, SY:352, BY:576), N=568, 284 unique prefixes
- 샘플링 200건: Y=100(FY:33, SY:33, BY:34), N=100, 171 unique prefixes
- batch-001: Y=50, N=50 (92 unique prefixes)
- batch-002: Y=50, N=50 (91 unique prefixes)
- 성별/연령/촬영환경 다양성 확보
