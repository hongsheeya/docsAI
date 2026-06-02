# FallAI 브랜딩 및 RF-Dual 운영 문서 정렬

- **ID**: 003
- **날짜**: 2026-04-15
- **유형**: 문서 업데이트

## 작업 요약
브라우저 탭/PWA 타이틀과 아이콘을 FallAI 기준으로 교체하고, 주요 상세 페이지 헤더를 공통 스타일로 정리했다.
동시에 파이프라인·관리자 메타데이터·문서 설명을 현재 실제 운영 구조인 RF-Dual 최종 판정 + XG-Posture 설명 레이어 기준으로 최신화했다.

## 변경 파일 목록
### 브랜딩 / PWA
- `src/assets/brand/fallai-mark.svg`: 새 브랜드 아이콘 추가
- `src/angular/index.pug`: 브라우저 탭 제목과 favicon 교체
- `src/assets/pwa/manifest.json`: PWA 이름/아이콘을 FallAI 기준으로 변경
- `config/season.py`: PWA 제목/아이콘 경로 갱신

### UI 헤더 정리
- `src/app/page.dashboard/view.pug`: 상단 아이콘과 버튼 라벨 정리
- `src/app/page.pipeline/view.pug`: 상단 헤더와 운영 모델 설명 정리
- `src/app/page.manual/view.pug`: 설명서 헤더 통일
- `src/app/page.admin.analysis/view.pug`: 관리자 헤더 통일
- `src/app/page.members/view.pug`: 멤버 헤더 통일
- `src/app/page.mypage/view.pug`: 내 프로필 헤더 통일
- `src/portal/post/app/list/view.pug`: 게시물 목록 헤더 통일
- `src/portal/post/app/detail/view.pug`: 게시물 상세 헤더 통일

### 운영 메타데이터 / 문서 최신화
- `src/model/struct/video_analysis.py`: 분석 엔진 요약, 진단, 실시간 청크 설명, 모델 설명, dataset summary를 RF-Dual 현재 운영 기준으로 정리
- `README.md`: 프로젝트 제목을 FallAI 기준으로 갱신
- `PROJECT_OVERVIEW.md`: 현재 서비스 설명과 실시간 청크 운영 문구 갱신
- `docs/prototype/fall-detection/camera-transition-plan.md`: 5초 청크 운영 기준 반영
