# 실시간 분석 가능 여부 검토 및 적용

- **ID**: 001
- **날짜**: 2026-03-25
- **유형**: 기능 추가

## 작업 요약
브라우저 스트림 샘플링 기반 실시간 분석이 현재 업로드 파이프라인 위에서 바로 가능한 범위를 정리하고, 그 범위를 메인페이지와 관리자 페이지에 반영했다. 분석 실행 영역 좌측에 영상 창을 고정하고 학습 데이터/모델 설명 정보를 함께 노출하도록 정리했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
- `src/app/page.dashboard/`
- `src/app/page.admin.analysis/`
- `src/app/component.nav.sidebar/view.pug`
