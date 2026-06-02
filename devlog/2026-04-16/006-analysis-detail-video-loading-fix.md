# 분석 상세 부분 영상 로딩 지연 수정

- **ID**: 006
- **날짜**: 2026-04-16
- **유형**: 버그 수정

## 작업 요약
분석 상세에서 부분 영상을 열 때 서버가 청크 클립을 즉석 재인코딩하면서 로딩이 길어지고 브라우저 재생도 불안정하던 문제를 수정했다.
업로드 로그는 원본 영상을 바로 스트리밍하고, 프론트엔드에서 청크 시작/종료 시각만 제어해 부분 구간처럼 재생하도록 변경했다.

## 변경 파일 목록
### 프론트엔드
- `src/app/page.dashboard/view.ts`
  - 분석 상세 비디오 모드를 `blob`/`upload`로 분리했다.
  - 업로드 로그는 원본 영상 URL을 사용하고 청크 구간 시작/종료 시각만 제어하도록 변경했다.
- `src/app/page.dashboard/view.pug`
  - `loadedmetadata`, `timeupdate` 기반으로 구간 재생하도록 수정했다.
  - 구간 안내 문구를 추가했다.

### 백엔드 API
- `src/app/page.dashboard/api.py`
  - 원본 업로드 영상을 바로 전달하는 `analysis_video_info`, `analysis_video` 엔드포인트를 추가했다.

### 모델/로직
- `src/model/struct/video_analysis.py`
  - 저장된 업로드 영상 경로를 안전하게 조회하는 `upload_video_info()`를 추가했다.
