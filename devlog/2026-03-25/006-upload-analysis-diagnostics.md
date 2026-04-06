# 업로드 분석 진단 정보 보강

- **ID**: 006
- **날짜**: 2026-03-25
- **유형**: 버그 수정

## 작업 요약
영상 분석이 제대로 동작하지 않는 원인을 확인할 수 있도록 백엔드 진단 정보를 추가했다. 학습 모델 부재, OpenCV 미설치, 실시간 아카이브 미누적 등 현재 품질 저하 요인을 메인페이지와 관리자 화면에서 직접 확인할 수 있게 정리했다.

## 변경 파일 목록
- `src/model/struct/video_analysis.py`
- `src/app/page.dashboard/view.pug`
- `src/app/page.admin.analysis/view.pug`
- `src/app/page.pipeline/view.pug`
