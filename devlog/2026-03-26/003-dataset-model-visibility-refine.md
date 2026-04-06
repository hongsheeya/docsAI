# 학습 데이터 수량 및 모델 표시 정비

- **ID**: 003
- **날짜**: 2026-03-26
- **유형**: UI 개선

## 작업 요약
학습 데이터 수량과 실제 운영 중인 분석 모델/fallback 상태를 명확히 표시하도록 백엔드 응답과 화면 구성을 정비했다. 낙상 모델, 행동 모델, 분석 아카이브의 의미를 메인·관리자·파이프라인 페이지에서 일관되게 노출하도록 맞췄다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
- `src/app/page.dashboard/view.pug`
- `src/app/page.admin.analysis/view.pug`
- `src/app/page.pipeline/view.pug`
