# 낙상영상 검증 리포트 삭제

- **ID**: 008
- **날짜**: 2026-03-26
- **유형**: 설정 변경

## 작업 요약
과적합된 모델의 `/낙상영상` 검증 리포트(`validation_report.json`)를 삭제. 백엔드 `_validation_summary()`가 리포트 미존재 시 'not-run' 상태를 자동 반환하므로 UI 코드 변경 불필요.

## 변경 파일 목록
### 삭제
- `storage/training/fall-detection/model/validation_report.json`: 과적합 모델 검증 결과 (accuracy 45.5%) 삭제
