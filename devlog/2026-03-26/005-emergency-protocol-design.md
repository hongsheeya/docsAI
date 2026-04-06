# 낙상 시 응급 프로토콜 설계 반영

- **ID**: 005
- **날짜**: 2026-03-26
- **유형**: 기능 추가

## 작업 요약
낙상 감지 시 대응 단계를 `주의`와 `고위험` 수준으로 나눠 응급 프로토콜 구조를 정의했다. 보호자 알림, 119 안내, 기록 항목을 백엔드에서 공통 데이터로 제공하고 메인·관리자·파이프라인 화면에 노출했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
- `src/app/page.dashboard/view.pug`
- `src/app/page.admin.analysis/view.pug`
- `src/app/page.pipeline/view.pug`
