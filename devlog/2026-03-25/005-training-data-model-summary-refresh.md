# 학습 데이터 요약 및 모델 설명 정비

- **ID**: 005
- **날짜**: 2026-03-25
- **유형**: 기능 추가

## 작업 요약
학습 데이터 요약과 현재 사용 중인 분석 엔진 설명을 다시 정리했다. 실제 학습 모델 파일 존재 여부와 fallback 동작을 구분해 메인페이지·관리자·파이프라인 페이지에서 같은 기준으로 설명하도록 맞췄다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
- `src/app/page.dashboard/view.pug`
- `src/app/page.admin.analysis/view.pug`
- `src/app/page.pipeline/`
