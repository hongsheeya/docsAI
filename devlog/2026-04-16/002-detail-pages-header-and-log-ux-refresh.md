# 세부 페이지 헤더 통일 및 로그 UX 개선

- **ID**: 002
- **날짜**: 2026-04-16
- **유형**: 기능 추가

## 작업 요약
세부 페이지 헤더에서 불필요한 메인 이동 버튼을 제거해 레이아웃을 통일했다.
파이프라인 페이지 문구를 RF-Dual 운영 기준으로 정리하고, 설명서 좌측 목차를 sticky 처리했으며, 업로드 분할 로그에는 청크 타임라인 시각화를 추가했다.

## 변경 파일 목록
### 프론트엔드
- `src/app/page.dashboard/view.ts`: 청크 타임라인 계산 헬퍼 추가, 속도/정책 문구 갱신
- `src/app/page.dashboard/view.pug`: 업로드 분할 로그 타임라인 시각화 추가, 실시간 청크 배지 수정
- `src/app/page.pipeline/view.pug`: 헤더 정리, 청크 정책/운영 역할 UI 개선
- `src/app/page.manual/view.pug`: 헤더 단순화, 좌측 목차 sticky 처리, 최신 청크 정책 반영
- `src/app/page.admin.analysis/view.pug`: 헤더 통일, XG-Fall 모니터링 제거 후 청크 운영 모니터링으로 교체
- `src/app/page.admin.analysis/view.ts`: 제거된 XG-Fall 보조 헬퍼 정리
