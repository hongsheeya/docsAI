# RF-Dual UI·로그·청크 정책 정리

- **ID**: 002
- **날짜**: 2026-04-15
- **유형**: 기능 추가

## 작업 요약
RF-Dual 낙상 판단 기준과 XG-Posture의 역할을 파이프라인/매뉴얼/프로토타입 문서에 반영했다. 업로드 분석에도 분할 청크 로그와 한 줄 설명을 추가하고, Dense Bootstrap(0~2 / 0~4 / 0~5초 후 5초 전환) 정책을 백엔드/프론트엔드에 연결했다.

## 변경 파일 목록

### 백엔드
- `src/model/struct/video_analysis.py`
  - 청크 정책 메타데이터(`chunk_policy`)와 낙상 판단 기준(`fall_decision_criteria`)을 `prototype_info()`에 추가
  - 공통 로그 요약 생성, 업로드 분할 청크 분석, 업로드 메타 JSON 기록 로직 추가
  - 실시간/업로드 응답에 `log_summary`를 포함하도록 확장

### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - Dense Bootstrap 기반 실시간 청크 스케줄링, 청크 윈도우 메타데이터, 업로드 로그 상태 추가
  - 업로드 결과의 분할 로그를 UI에 매핑하는 공통 로그 엔트리 헬퍼 추가
- `src/app/page.dashboard/view.pug`
  - 상단 브랜드/아이콘 갱신
  - 실시간 로그에 한 줄 설명 표시
  - 업로드 모드 분할 로그 리스트 및 정책 안내 카드 추가
  - 로그 상세 모달에 청크 구간/한 줄 설명 표시
- `src/app/page.pipeline/view.pug`
  - 메인 페이지 스타일과 통일된 헤더로 개편
  - 낙상 판단 기준, XG-Posture 역할, 청크 정책 설명 섹션 추가
- `src/app/page.manual/view.pug`
  - 헤더 스타일 통일
  - RF-Dual 판단 기준, 업로드/실시간 청크 정책, 로그 설명을 최신 운영 방식에 맞게 갱신
- `src/app/component.nav.sidebar/view.pug`
  - 사이드바 서비스 타이틀/소개 문구 교체

### 문서
- `docs/prototype/fall-detection/README.md`
  - RF-Dual 판단 기준, XG-Posture 필요성, Dense Bootstrap 청크 정책, 로그 정책 문서화

## 검증
- VS Code 진단 기준 오류 없음 (`video_analysis.py`, `page.dashboard/view.ts`, `page.dashboard/view.pug`, `page.pipeline/view.pug`, `page.manual/view.pug`)
